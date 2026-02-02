import json

class GraphCompiler:
    """
    Compiles the visual SvelteFlow graph into:
    1. Triggers list (for efficient event filtering).
    2. JsonLogic rules (for actual evaluation).
    """

    @staticmethod
    def compile(graph_data):
        """
        :param graph_data: Dict { "nodes": [...], "edges": [...] }
        :return: (triggers_list, compiled_logic)
        """
        if not graph_data or 'nodes' not in graph_data:
            return [], {}

        nodes = {n['id']: n for n in graph_data['nodes']}
        edges = graph_data.get('edges', [])

        trigger_nodes = [n for n in nodes.values() if n['type'] == 'trigger']
        triggers = []

        for t_node in trigger_nodes:
            data = t_node.get('data', {})
            trigger_type = data.get('trigger')
            params = {}
            
            if trigger_type == 'ON_LESSON_COMPLETE':
                params['lesson_id'] = data.get('lesson_id') 
            elif trigger_type == 'ON_COURSE_COMPLETE':
                params['course_id'] = data.get('course_id')
            elif trigger_type == 'ON_SECTION_COMPLETE':
                params['section_id'] = data.get('section_id')
            elif trigger_type == 'ON_TEST_PASSED':
                params['test_id'] = data.get('test_id')
            elif trigger_type in ['ON_TERM_LEARNED', 'ON_WORD_LEARNED']:
                params['entry_id'] = data.get('entry_id')
            elif trigger_type == 'PERIODIC_CHECK':
                params['frequency'] = data.get('frequency')
            
            triggers.append({
                'type': trigger_type,
                'params': params
            })

        incoming_map = {}
        for edge in edges:
            target = edge['target']
            source = edge['source']
            if target not in incoming_map:
                incoming_map[target] = []
            incoming_map[target].append(source)

        memo = {} 

        def compile_node(node_id):
            if node_id in memo:
                return memo[node_id]
            
            node = nodes.get(node_id)
            if not node:
                return True 

            node_type = node['type']
            data = node.get('data', {})

            if node_type == 'trigger':
                return True

            sources = incoming_map.get(node_id, [])
            
            input_logics = [compile_node(src) for src in sources]
            
            real_inputs = [l for l in input_logics if l is not True]
            
            current_logic = None

            if node_type == 'condition':
                # { "operator": [ { "var": "fact" }, "value" ] }
                var = data.get('variable')
                op = data.get('operator')
                val = data.get('value')
                
                try:
                    if "." in str(val):
                        val = float(val)
                    else:
                        val = int(val)
                except:
                    pass

                current_logic = { op: [ { "var": var }, val ] }

            elif node_type == 'logic':
                logic_type = data.get('logic_type', 'AND') # AND / OR
                op = "and" if logic_type == 'AND' else "or"
                
                if not real_inputs:
                    current_logic = True # No inputs?
                elif len(real_inputs) == 1:
                    current_logic = real_inputs[0]
                else:
                    current_logic = { op: real_inputs }

            elif node_type == 'time':
               
                start_time = data.get('start_time') # "18:00"
                end_time = data.get('end_time')     # "21:00"
                days = data.get('days', [])         # [0, 6] (Mon=0)
                
                conditions = []
                
                if start_time and end_time:
                    s_h = int(start_time.split(':')[0])
                    e_h = int(end_time.split(':')[0])
                    
                    # { "<=": [ s_h, { "var": "time.hour" }, e_h ] } 
                    # { "and": [ { ">=": [ {"var": "time.hour"}, s_h ] }, { "<=": [ {"var": "time.hour"}, e_h ] } ] }
                    conditions.append({
                        "and": [
                            { ">=": [ { "var": "time.hour" }, s_h ] },
                            { "<=": [ { "var": "time.hour" }, e_h ] }
                        ]
                    })

                if days:
                    # { "in": [ { "var": "time.weekday" }, days ] }
                    conditions.append({
                        "in": [ { "var": "time.weekday" }, days ]
                    })
                
                if not conditions:
                    current_logic = True
                elif len(conditions) == 1:
                    current_logic = conditions[0]
                else:
                    current_logic = { "and": conditions }

            elif node_type == 'range':
                var = data.get('variable')
                min_v = data.get('min')
                max_v = data.get('max')
                
                try:
                    min_v = float(min_v)
                    max_v = float(max_v)
                except:
                    pass

                current_logic = {
                    "and": [
                        { ">=": [ { "var": var }, min_v ] },
                        { "<=": [ { "var": var }, max_v ] }
                    ]
                }
                
            elif node_type == 'achievement_check':
                target_id = data.get('achievement_id')
                current_logic = {
                    "in": [ target_id, { "var": "user.achievements" } ]
                }

            else:
                current_logic = True

            if node_type != 'logic' and real_inputs:
                # Implicit AND
                combined = [current_logic] + real_inputs
                current_logic = { "and": combined }
            
            memo[node_id] = current_logic
            return current_logic

        source_nodes = set()
        for edge in edges:
            source_nodes.add(edge['source'])
        
        terminal_nodes = [nid for nid in nodes if nid not in source_nodes]
        
        terminal_nodes = [nid for nid in terminal_nodes if nodes[nid]['type'] != 'trigger']

        if not terminal_nodes:
         
            if triggers:
                return triggers, True
            return triggers, False

        final_logics = [compile_node(nid) for nid in terminal_nodes]
        
        if len(final_logics) == 1:
            compiled_rules = final_logics[0]
        else:
            compiled_rules = { "and": final_logics }

        return triggers, compiled_rules
