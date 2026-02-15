import os
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand
from django.conf import settings
from dict_service.models import KanjiCharacter, KanjiStructure
from django.db import transaction

class Command(BaseCommand):
    help = 'Parses KanjiVG SVG files and populates KanjiCharacter and KanjiStructure models efficiently'

    def handle(self, *args, **options):
        try:
            self._handle(*args, **options)
        except Exception as e:
            import traceback
            self.stdout.write(self.style.ERROR(f"Error during import: {e}"))
            traceback.print_exc()

    def _handle(self, *args, **options):
        kanji_dir = os.path.join(settings.BASE_DIR, 'static', 'kanji')
        if not os.path.exists(kanji_dir):
            self.stdout.write(self.style.ERROR(f'Directory not found: {kanji_dir}'))
            return

        svg_files = [f for f in os.listdir(kanji_dir) if f.endswith('.svg')]
        self.stdout.write(f'Found {len(svg_files)} SVG files')

        all_chars_set = set()
        all_pairs = set() # (parent_str, child_str)

        self.stdout.write('Step 1: Parsing SVGs and building local trees...')
        char_trees = {}
        all_chars_set = set()
        all_pairs = set() # (parent_str, child_str)

        for i, filename in enumerate(svg_files):
            if i % 1000 == 0:
                self.stdout.write(f"Parsing: {i}/{len(svg_files)}")
            file_path = os.path.join(kanji_dir, filename)
            try:
                tree_et = ET.parse(file_path)
                root = tree_et.getroot()
                
                main_g = None
                for g in root.findall('.//{http://www.w3.org/2000/svg}g'):
                    if '{http://kanjivg.tagaini.net}element' in g.attrib:
                        main_g = g
                        break
                
                if main_g is not None:
                    main_char_str = main_g.attrib.get('{http://kanjivg.tagaini.net}element')
                    if main_char_str:
                        all_chars_set.add(main_char_str)
                        # Build tree and collect pairs for this specific character SVG
                        tree_data, pairs = self.parse_svg_structure(main_g, main_char_str)
                        char_trees[main_char_str] = tree_data
                        all_pairs.update(pairs)
            except Exception:
                continue

        self.stdout.write(f'Step 2: Syncing {len(all_chars_set)} characters to database...')
        
        existing_chars = KanjiCharacter.objects.only('id', 'character')
        existing_map = {c.character: c for c in existing_chars}
        
        new_chars = [KanjiCharacter(character=c) for c in all_chars_set if c not in existing_map]
        
        if new_chars:
            self.stdout.write(f'Creating {len(new_chars)} new characters...')
            KanjiCharacter.objects.bulk_create(new_chars, batch_size=500)

        # Refresh map with all characters
        all_chars = KanjiCharacter.objects.only('id', 'character')
        char_obj_map = {c.character: c for c in all_chars}

        self.stdout.write(f'Step 3: Syncing {len(all_pairs)} structures...')
        structure_objs = []
        for p_str, c_str in all_pairs:
            p_obj = char_obj_map.get(p_str)
            c_obj = char_obj_map.get(c_str)
            if p_obj and c_obj and p_obj.id != c_obj.id:
                structure_objs.append(KanjiStructure(parent=p_obj, child=c_obj))

        with transaction.atomic():
            KanjiStructure.objects.all().delete()
            KanjiStructure.objects.bulk_create(structure_objs, batch_size=1000)

        self.stdout.write('Step 4: Saving decomposition trees...')
        to_update = []
        for char_str, tree_data in char_trees.items():
            char_obj = char_obj_map.get(char_str)
            if char_obj:
                char_obj.decomposition_tree = tree_data
                to_update.append(char_obj)
                if len(to_update) >= 500:
                    KanjiCharacter.objects.bulk_update(to_update, ['decomposition_tree'], batch_size=100)
                    to_update = []
        
        if to_update:
            KanjiCharacter.objects.bulk_update(to_update, ['decomposition_tree'], batch_size=100)

        self.stdout.write(self.style.SUCCESS('Import complete!'))

    def parse_svg_structure(self, element, current_parent):
        """Recursively builds decomposition tree from SVG groups."""
        char = element.attrib.get('{http://kanjivg.tagaini.net}element') or element.attrib.get('{http://kanjivg.tagaini.net}original') or "?"
        
        children_data = []
        pairs = set()
        
        for child in element:
            if child.tag == '{http://www.w3.org/2000/svg}g':
                child_char = child.attrib.get('{http://kanjivg.tagaini.net}element')
                if child_char:
                    # Avoid redundant nodes (same character or parts)
                    if child_char == char or child_char == current_parent:
                        child_tree, child_pairs = self.parse_svg_structure(child, current_parent)
                        children_data.extend(child_tree['children'])
                        pairs.update(child_pairs)
                    else:
                        child_tree, child_pairs = self.parse_svg_structure(child, child_char)
                        # Filter CDP placeholder labels or generic "?"
                        if child_char.startswith('CDP-') or child_char == '?':
                            children_data.extend(child_tree['children'])
                        else:
                            children_data.append(child_tree)
                            pairs.add((current_parent, child_char))
                        pairs.update(child_pairs)
                else:
                    # Group without label, look inside
                    child_tree, child_pairs = self.parse_svg_structure(child, current_parent)
                    children_data.extend(child_tree['children'])
                    pairs.update(child_pairs)
        
        return {"character": char, "children": children_data}, pairs

