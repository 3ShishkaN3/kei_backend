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

        # 1. Find Trigger Nodes
        trigger_nodes = [n for n in nodes.values() if n['type'] == 'trigger']
        triggers = []

        for t_node in trigger_nodes:
            data = t_node.get('data', {})
            trigger_type = data.get('trigger')
            params = {}
            
            # Extract parameters based on trigger type
            if trigger_type == 'ON_LESSON_COMPLETE':
                params['lesson_id'] = data.get('lesson_id') # Can be None (Any)
            elif trigger_type == 'ON_COURSE_COMPLETE':
                params['course_id'] = data.get('course_id')
            elif trigger_type == 'ON_SECTION_COMPLETE':
                params['section_id'] = data.get('section_id')
            elif trigger_type == 'ON_TEST_PASSED':
                params['test_id'] = data.get('test_id')
            elif trigger_type == 'PERIODIC_CHECK':
                params['frequency'] = data.get('frequency')
            
            triggers.append({
                'type': trigger_type,
                'params': params
            })

        # 2. Build Logic Tree
        # We start from the triggers and follow edges to conditions.
        # However, SvelteFlow is a graph. JsonLogic is a tree.
        # We need to find the "root" of the condition logic.
        # Usually, in this editor, multiple conditions are implicitly AND-ed 
        # or connected via Logic Nodes.
        
        # Strategy:
        # 1. Find all nodes that are NOT triggers but have incoming edges from Triggers (or are roots of condition trees).
        # Actually, a better approach for this specific editor style (flowchart):
        # We can treat the graph as a set of conditions that MUST ALL be true (Implicit AND),
        # UNLESS there are explicit LogicNodes.
        
        # Let's traverse from the "end" nodes back to the start? 
        # Or simpler: Find all "Condition", "Logic", "Time", "Range", "AchievementCheck" nodes.
        # If there are multiple disconnected trees, we assume they are AND-ed.
        
        # But wait, the structure is: Trigger -> Condition -> Condition -> ...
        # If we have multiple Triggers, any of them can start the chain?
        # Usually, Triggers just initiate the check. The Conditions check the state.
        
        # Let's assume all Condition/Logic nodes in the graph must evaluate to True 
        # for the achievement to be awarded? 
        # No, that prevents "OR" logic if nodes are disconnected.
        
        # Let's look at the edges.
        # If we have a Logic Node (AND/OR), it will have inputs.
        # If we have a Condition Node, it might be a leaf or part of a chain.
        
        # REVISED STRATEGY:
        # We need to find the "Terminal" nodes - nodes that don't have outgoing edges to other condition nodes.
        # (Trigger nodes are sources. Conditions are intermediates/sinks).
        # If there are multiple terminal nodes, we AND them together.
        
        # Map: TargetNodeID -> [SourceNodeID]
        incoming_map = {}
        for edge in edges:
            target = edge['target']
            source = edge['source']
            if target not in incoming_map:
                incoming_map[target] = []
            incoming_map[target].append(source)

        # Helper to compile a specific node
        memo = {} # To avoid re-compiling if referenced multiple times (DAG)

        def compile_node(node_id):
            if node_id in memo:
                return memo[node_id]
            
            node = nodes.get(node_id)
            if not node:
                return True # Should not happen

            node_type = node['type']
            data = node.get('data', {})

            # TRIGGER NODE: Always True (it just started the process)
            if node_type == 'trigger':
                return True

            # RECURSIVE STEP: Get inputs
            sources = incoming_map.get(node_id, [])
            
            # If no sources, and it's not a trigger... 
            # It might be a floating condition? 
            # In standard logic, floating conditions are usually ignored or assumed True.
            # But here, if a user adds a condition, they probably want it checked.
            # Let's assume if it has NO incoming edges, it's a root condition.
            
            input_logics = [compile_node(src) for src in sources]
            
            # Filter out "True" from triggers (we don't need { "and": [True, ...] })
            # But if ALL inputs are triggers, we proceed with the node's own logic.
            real_inputs = [l for l in input_logics if l is not True]
            
            current_logic = None

            if node_type == 'condition':
                # { "operator": [ { "var": "fact" }, "value" ] }
                var = data.get('variable')
                op = data.get('operator')
                val = data.get('value')
                
                # Convert value to number if possible
                try:
                    if "." in str(val):
                        val = float(val)
                    else:
                        val = int(val)
                except:
                    pass # Keep as string

                current_logic = { op: [ { "var": var }, val ] }

            elif node_type == 'logic':
                logic_type = data.get('logic_type', 'AND') # AND / OR
                op = "and" if logic_type == 'AND' else "or"
                
                # Logic node combines its inputs. 
                # But wait, Logic Node usually sits BETWEEN conditions?
                # Or does it aggregate them?
                # If Logic Node has inputs A and B, it returns (A op B).
                if not real_inputs:
                    current_logic = True # No inputs?
                elif len(real_inputs) == 1:
                    current_logic = real_inputs[0]
                else:
                    current_logic = { op: real_inputs }

            elif node_type == 'time':
                # Check server time
                # We'll use a custom json-logic operation or just standard vars if we inject time into context
                # Let's assume we inject "time.hour" and "time.weekday" into context
                
                start_time = data.get('start_time') # "18:00"
                end_time = data.get('end_time')     # "21:00"
                days = data.get('days', [])         # [0, 6] (Mon=0)
                
                conditions = []
                
                if start_time and end_time:
                    # Simple range check for hour (simplified)
                    s_h = int(start_time.split(':')[0])
                    e_h = int(end_time.split(':')[0])
                    
                    # { "<=": [ s_h, { "var": "time.hour" }, e_h ] } 
                    # JsonLogic doesn't support ternary comparison directly like python
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
                # We need to check if user has this achievement.
                # We can inject a list of user's achievement IDs into context: "user.achievements"
                current_logic = {
                    "in": [ target_id, { "var": "user.achievements" } ]
                }

            else:
                current_logic = True

            # If this node had inputs (and wasn't a Logic node which consumes them explicitly),
            # we implicitly AND them with the current node's logic.
            # (Unless it's a Logic node, which we handled above).
            
            if node_type != 'logic' and real_inputs:
                # Implicit AND
                combined = [current_logic] + real_inputs
                current_logic = { "and": combined }
            
            memo[node_id] = current_logic
            return current_logic

        # 3. Find Terminal Nodes
        # Nodes that are NOT sources for any edge
        source_nodes = set()
        for edge in edges:
            source_nodes.add(edge['source'])
        
        terminal_nodes = [nid for nid in nodes if nid not in source_nodes]
        
        # Filter out trigger nodes from terminals (if they are unconnected)
        terminal_nodes = [nid for nid in terminal_nodes if nodes[nid]['type'] != 'trigger']

        if not terminal_nodes:
            # If only triggers exist, return False (no conditions = no achievement?)
            # Or True? If I just want "On Lesson Complete" -> Award.
            # Let's assume True if there are triggers but no conditions.
            if triggers:
                return triggers, True
            return triggers, False

        final_logics = [compile_node(nid) for nid in terminal_nodes]
        
        if len(final_logics) == 1:
            compiled_rules = final_logics[0]
        else:
            compiled_rules = { "and": final_logics }

        return triggers, compiled_rules
