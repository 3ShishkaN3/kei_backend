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

        self.stdout.write('Step 1: Parsing SVGs in memory...')
        for i, filename in enumerate(svg_files):
            if i % 1000 == 0:
                self.stdout.write(f"Parsing: {i}/{len(svg_files)}")
            file_path = os.path.join(kanji_dir, filename)
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                
                main_g = None
                for g in root.iter('{http://www.w3.org/2000/svg}g'):
                    if '{http://kanjivg.tagaini.net}element' in g.attrib:
                        main_g = g
                        break
                
                if main_g is not None:
                    main_char_str = main_g.attrib.get('{http://kanjivg.tagaini.net}element')
                    if main_char_str:
                        all_chars_set.add(main_char_str)
                        self.collect_pairs(main_g, main_char_str, all_chars_set, all_pairs)
            except Exception:
                continue

        self.stdout.write(f'Step 2: Syncing {len(all_chars_set)} characters to database...')
        
        existing_chars = set(KanjiCharacter.objects.values_list('character', flat=True))
        new_chars = [KanjiCharacter(character=c) for c in all_chars_set if c not in existing_chars]
        
        if new_chars:
            self.stdout.write(f'Creating {len(new_chars)} new characters in batches of 500...')
            KanjiCharacter.objects.bulk_create(new_chars, batch_size=500)
            self.stdout.write(f'Successfully created characters.')

        char_obj_map = {c.character: c.id for c in KanjiCharacter.objects.only('id', 'character')}

        self.stdout.write(f'Step 3: Syncing {len(all_pairs)} structures to database...')
        structure_objs = []
        for p_str, c_str in all_pairs:
            p_id = char_obj_map.get(p_str)
            c_id = char_obj_map.get(c_str)
            if p_id and c_id and p_id != c_id:
                structure_objs.append(KanjiStructure(parent_id=p_id, child_id=c_id))

        with transaction.atomic():
            KanjiStructure.objects.all().delete()
            KanjiStructure.objects.bulk_create(structure_objs, batch_size=1000)

        self.stdout.write('Step 4: Building decomposition trees...')
        struct_map = {}
        for p_str, c_str in all_pairs:
            p_id = char_obj_map.get(p_str)
            c_id = char_obj_map.get(c_str)
            if p_id and c_id and p_id != c_id:
                if p_id not in struct_map:
                    struct_map[p_id] = []
                if c_id not in struct_map[p_id]:
                    struct_map[p_id].append(c_id)

        tree_cache = {}
        char_id_to_str = {v: k for k, v in char_obj_map.items()}
        
        characters = KanjiCharacter.objects.only('id', 'character')
        to_update = []
        char_count = characters.count()
        
        for i, char in enumerate(characters):
            if i % 1000 == 0:
                self.stdout.write(f'Processing trees: {i}/{char_count}')
            
            char.decomposition_tree = self.get_tree(char.id, struct_map, char_id_to_str, set(), tree_cache)
            to_update.append(char)
            
            if len(to_update) >= 500:
                KanjiCharacter.objects.bulk_update(to_update, ['decomposition_tree'], batch_size=100)
                to_update = []

        if to_update:
            KanjiCharacter.objects.bulk_update(to_update, ['decomposition_tree'], batch_size=100)

        self.stdout.write(self.style.SUCCESS('Import complete!'))

    def collect_pairs(self, element, parent_str, all_chars_set, all_pairs):
        for child in element:
            if child.tag == '{http://www.w3.org/2000/svg}g':
                child_char_str = child.attrib.get('{http://kanjivg.tagaini.net}element')
                if child_char_str:
                    all_chars_set.add(child_char_str)
                    all_pairs.add((parent_str, child_char_str))
                    self.collect_pairs(child, child_char_str, all_chars_set, all_pairs)
                else:
                    self.collect_pairs(child, parent_str, all_chars_set, all_pairs)

    def get_tree(self, char_id, struct_map, char_id_to_str, visited, tree_cache):
        
        char_str = char_id_to_str.get(char_id, "?")
        
        if char_id in visited:
            return {"character": char_str, "children": []}

        if char_id in tree_cache:
            return tree_cache[char_id]

        visited.add(char_id)
        children_ids = struct_map.get(char_id, [])
        children_data = []
        
        for c_id in children_ids:
            child_tree = self.get_tree(c_id, struct_map, char_id_to_str, visited.copy(), tree_cache)
            if child_tree:
                children_data.append(child_tree)
        
        res = {
            "character": char_str,
            "children": children_data
        }
        
        tree_cache[char_id] = res
        return res
