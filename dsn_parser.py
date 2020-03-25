"""
DSN Parser.

Usage:
    dsn_parser.py <dsn_file> <output_file>

"""

from docopt import docopt


netclass_preamble = """
  (net_class Default "This is the default net class."
    (clearance 0.127)
    (trace_width 0.127)
    (via_dia 0.3524)
    (via_drill 0.2)
    (uvia_dia 0.3)
    (uvia_drill 0.1)"""

scale_factor = 0.0254 # converts from mils to mm
component_x_offset = 100 # try to get things in the middle of the page, just for convience
component_y_offset = 100

def scale_str(s):
    return str(float(s) * scale_factor)

class Node(object):
    """
    S-expression node class. Has parents, children, and text. Doesn't handle quoted escapes yet but it should in the future.
    """
    def __init__(self, text='', parent=None, children=None, t_start=0, t_end=0):
        self.text = text
        self.t_start = t_start
        self.t_end = t_end
        self.parent = parent
        if self.parent is not None:
            self.parent.children.append(self)

        if children is None:
            self.children = []

    def add_c(self, c):
        self.text += c
        if self.parent is not None:
            
            self.parent.add_c(c)

    def keyword(self):
        if len(self.text) > 0:
            return self.text.split()[0].strip('()')
        else:
            return ''

    def word(self, i):
        return self.text.strip().strip('()').split()[i].strip('()')


def get_keywords(text):
    # find keywords
    splits = text.split('(')
    splits = [s.split() for s in splits]
    keywords = set()
    for s in splits:
        if len(s) > 0:
            keywords.add(s[0])

    keywords = list(keywords)
    keywords.sort()
    return keywords


def main(arguments):
    print(arguments)

    with open(arguments['<dsn_file>'], 'r') as f:
        text = f.read()

    node_stack = []
    nodes = []
    for i, c in enumerate(text):
        if c == '(':
            # print(str(len(nodes)), 'New node:', text[i:i+15].strip())
            if len(node_stack) > 0:
                node_stack.append(Node(parent=node_stack[-1]))
            else:
                node_stack.append(Node())
            node_stack[-1].t_start = i
            nodes.append(node_stack[-1])
        elif c == ')':
            node_stack[-1].t_end = i+1
            node_stack.pop()

    node_types = {}
    for n in nodes:
        n.text = text[n.t_start:n.t_end]
        # print(n.keyword(), n.text)
        try:
            node_types[n.keyword()].append(n)
        except KeyError:
            node_types[n.keyword()] = [n]
    

    images = {}
    for n in node_types['image']:
        image_name = n.word(1)
        images[image_name] = n

    padstacks = {}
    for n in node_types['padstack']:
        padstack_name = n.word(1)
        padstacks[padstack_name] = n

    nets = {}
    kicad_nets = []
    netclass_str = netclass_preamble
    pins_to_nets = {}
    net_name_to_net_number = {}
    pin_counts = {}
    for n in node_types['net']:
        net_name = n.word(1)
        net_name_to_net_number[net_name] = len(kicad_nets)
        kicad_nets.append('(net ' + str(len(kicad_nets)) + ' ' + net_name + ')')
        netclass_str += '\n    (add_net ' + net_name + ')'
        pins = [c for c in n.children if c.keyword() == 'pins']
        assert len(pins) < 2, 'Non-singular pin list in net: ' + n.text
        # assert len(pins) > 0, 'No pin list in net: ' + n.text
        if len(pins) == 0:
            break
        pins = pins[0]
        assert pins.keyword() == 'pins'
        print(net_name)
        pin_names = pins.text.strip().strip('()').split()[1:]
        print(pin_names)
        pins = []
        for p in pin_names:
            ps = p.split('-')
            assert len(ps) == 2, 'Bad format for pin designator: ' + p
            component_name = ps[0]
            pin_number = ps[1]
            print('\t', component_name, pin_number)
            pins_to_nets[(component_name, pin_number)] = net_name
            try:
                pin_counts[net_name] += 1
            except KeyError:
                pin_counts[net_name] = 1

    netclass_str += '\n  )'


    shape_types = set()

    components = {}
    kicad_module_strs = []
    for n in node_types['component']:
        module_str = '(module '
        print(n.text)
        image_name = n.word(1)

        # assert image_name not in components, 'Got duplicate image name: ' + image_name
        place = [p for p in n.children if p.keyword() == 'place']
        assert len(place) == 1, 'Did not get a singular place for component ' + image_name
        place = place[0]
        ref_des = place.word(1)
        components[ref_des] = n
        x = str(float(scale_str(place.word(2))) + component_x_offset)
        y = str(float(scale_str(place.word(3))) + component_y_offset)
        side = place.word(4)
        rotation = place.word(5)
        rotation = str(-float(rotation))
        print(image_name, ref_des, x, y, side, rotation)
        print('Component rotation:', rotation)

        module_str += ref_des
        mirrored = False
        if side.lower() == 'front':
            side = 'Top'
        elif side.lower() == 'back':
            side = 'Bottom'
            mirrored = True
        else:
            raise Exception('Unrecognized side: ' + str(module_str))
        module_str += ' (layer ' + side.lower().capitalize() + ')'
        module_str += '\n'
        module_str += '    (at ' + str(x) + ' ' + str(y) + ' ' + str(rotation) + ')'
        module_str += '\n'
        module_str += '    (fp_text reference "' + ref_des + '" (at 0 0 ' + str(rotation) + ') (layer F.SilkS))'
        module_str += '\n'

        image = images[image_name]
        # print(image.text)
        pads = [p for p in image.children if p.keyword() == 'pin']
        pad_strs = []
        for pad in pads:
            pad_str = ''
            padstack_name = pad.word(1)
            pad_num = pad.word(2)
            pad_x = scale_str(pad.word(3))
            pad_y = scale_str(pad.word(4))

            if mirrored:
                pad_x = str(-float(pad_x))
                # pad_y = str(-float(pad_y))

            padstack = padstacks[padstack_name]
            print('\tpad', padstack_name, pad_num, pad_x, pad_y)
            pad_type = [c for c in padstack.children if c.keyword() == 'type'][0].word(1)
            shapes = [s for s in padstack.children if s.keyword() == 'shape']

            pad_rotation = [c for c in pad.children if c.keyword() == 'rotate']
            if len(pad_rotation) == 1:
                pad_rotation = float(pad_rotation[0].word(1))
            else:
                pad_rotation = 0.0

            pad_rotation -= float(rotation)



    #(pad 1 smd roundrect (at -0.955 0 270) (size 0.92 1.38) (layers Top F.Mask) (roundrect_rratio 0.25)
      #(net 22 /RESET) (solder_mask_margin 0.0635))
            pad_str += '    (pad '
            pad_str += str(pad_num)
            if pad_type == 'smdpad':
                pad_str += ' smd'
            elif pad_type == 'thrupad':
                continue
                pad_str += ' thrupad not handled yet'
            else:
                raise Exception('Bad pad type: ' + pad_type)


            for s in shapes:
                assert len(s.children) == 1, "Multiple shape children: " + str(s.text)
                shape = s.children[0]
                shape_type = shape.keyword()
                shape_types.add(shape_type)
                print('\t\t' + shape_type + ' ' + s.text)

                # handle each shape seperately
                # This should be refactored so that there is less repeated code

                if shape_type == 'rect':
                    pad_str += ' rect'
                    layer = shape.word(1)
                    pad_str += f' (at {pad_x} {pad_y} {pad_rotation})'

                    width = float(scale_str(shape.word(2))) - float(scale_str(shape.word(4)))
                    width = abs(width)
                    height = float(scale_str(shape.word(3))) - float(scale_str(shape.word(5)))
                    height = abs(height)

                    pad_str += f' (size {width} {height})'

                    if side.lower() == 'bottom':
                        if layer.lower() == 'top':
                            layer = 'Bottom'
                        elif layer.lower() == 'bottom':
                            layer = 'Top'

                    pad_str += f' (layers {layer.lower().capitalize()})'
                    pin_key = (ref_des, pad_num)
                    if pin_key in pins_to_nets:
                        net = pins_to_nets[(ref_des, pad_num)]
                        net_num = net_name_to_net_number[net]
                        pad_str += f'\n      (net {net_num} {net})'

                    pad_str += ')\n'
                    module_str += pad_str

                elif shape_type == 'circle':
                    pad_str += ' circle'
                    layer = shape.word(1)
                    pad_str += f' (at {pad_x} {pad_y} {pad_rotation})'

                    width = float(scale_str(shape.word(2)))
                    pad_str += f' (size {width} {width})'

                    if side.lower() == 'bottom':
                        if layer.lower() == 'top':
                            layer = 'Bottom'
                        elif layer.lower() == 'bottom':
                            layer = 'Top'

                    pad_str += f' (layers {layer.lower().capitalize()})'
                    
                    pin_key = (ref_des, pad_num)
                    if pin_key in pins_to_nets:
                        net = pins_to_nets[(ref_des, pad_num)]
                        net_num = net_name_to_net_number[net]
                        pad_str += f'\n      (net {net_num} {net})'
                    # elif ref_des == 'U6':
                    #     print('#'*80)
                    #     print(n.text)
                    #     print('#'*80)
                    #     print(pin_key)
                    #     print('#'*80)
                    #     print([k for k in pins_to_nets.keys() if k[0] == 'U6'])
                    #     raise Exception('U6 Error')

                    pad_str += ')\n'
                    module_str += pad_str

                break # only one shape allowed in kicad?



        module_str += '  )'
        kicad_module_strs.append(module_str)

    print()
    print('Shape types: ' + str(shape_types))



    # wiring for viewing shapes
    zone_strings = []
    for n in node_types['wiring']:
        print('#'*80, 'Got wiring node', n)
        wires = [w for w in n.children if w.keyword() == 'wire']
        print('Got', len(wires), 'wires')
        polygons = []

        for w in wires:
            w_polys = [p for p in w.children if p.keyword() == 'polygon']
            polygons += w_polys

        for p in polygons:
            print(p.parent.text)

            print(p.text)
            layer = p.word(1).lower().capitalize()
            if layer == 'Lyr3':
                layer = 'Route2'
            if layer == 'Lyr4':
                layer = 'Route15'

            net_name = [n.word(1) for n in p.parent.children if n.keyword() == 'net']
            assert len(net_name) == 1
            net_name = net_name[0]
            assert p.word(2) == '0' # not sure what this field is
            points = []
            for point in p.text.split()[3:]:
                if point.startswith('('):
                    break
                points.append(point.strip().strip('()'))

            points = [float(t) for t in points]

            print(points)
            assert len(points) % 2 == 0

            """
              (zone (net 0) (net_name "") (layer F.SilkS) (tstamp 0) (hatch edge 0.508)
                (connect_pads (clearance 0.508))
                (min_thickness 0.254)
                (fill yes (arc_segments 32) (thermal_gap 0.508) (thermal_bridge_width 0.508))
                (polygon
                  (pts
                    (xy 104.68 101.83) (xy 99.93 70.51) (xy 135.22 70.11) (xy 148.7 98.66) (xy 124.91 129.19)
                  )
                )
              )
            """
            zone_str = """
  (zone (net """ + str(net_name_to_net_number[net_name]) + ') (layer ' + layer + """) (tstamp 0) (hatch edge 0.508)
    (connect_pads (clearance 0.508))
    (min_thickness 0.254)
    (fill yes (arc_segments 32) (thermal_gap 0.508) (thermal_bridge_width 0.508))
    (polygon
      (pts
   """
            point_index = 0
            for point in points:
                try:
                    x = scale_str(str(points[point_index]))
                    y = scale_str(str(points[point_index+1]))

                    x = str(float(x) + component_x_offset)
                    y = str(float(y) + component_y_offset)

                    zone_str += ' (xy ' + x
                    zone_str += ' ' + y + ')'
                except IndexError:
                    break
                point_index += 2
            zone_str += '\n    )))'
            print(zone_str)
            zone_strings.append(zone_str)


        print('Got', len(polygons), 'polygons')


    print()
    print('#'*80)
    kicad_str = '(kicad_pcb (version 20171130) (host pcbnew 5.1.5-52549c5~84~ubuntu18.04.1)'
    num_nets = len(kicad_nets)
    num_modules = len(kicad_module_strs)
    kicad_str += f"""

  (general
    (thickness 1.6)
    (drawings 0)
    (tracks 0)
    (zones 0)
    (modules {num_modules})
    (nets {num_nets})
  )

  (page A4)

  (layers
    (0 Top signal)
    (1 Route2 signal)
    (2 Route15 signal)
    (31 Bottom signal)
    (32 B.Adhes user)
    (33 F.Adhes user)
    (34 B.Paste user)
    (35 F.Paste user)
    (36 B.SilkS user)
    (37 F.SilkS user)
    (38 B.Mask user)
    (39 F.Mask user hide)
    (40 Dwgs.User user)
    (41 Cmts.User user)
    (42 Eco1.User user)
    (43 Eco2.User user)
    (44 Edge.Cuts user)
    (45 Margin user)
    (46 B.CrtYd user)
    (47 F.CrtYd user)
    (48 B.Fab user)
    (49 F.Fab user)
  )

  (setup
    (last_trace_width 0.127)
    (trace_clearance 0.127)
    (zone_clearance 0.508)
    (zone_45_only no)
    (trace_min 0.127)
    (via_size 0.3524)
    (via_drill 0.2)
    (via_min_size 0.2)
    (via_min_drill 0.2)
    (uvia_size 0.3)
    (uvia_drill 0.1)
    (uvias_allowed no)
    (uvia_min_size 0.2)
    (uvia_min_drill 0.1)
    (edge_width 0.05)
    (segment_width 0.2)
    (pcb_text_width 0.3)
    (pcb_text_size 1.5 1.5)
    (mod_edge_width 0.12)
    (mod_text_size 1 1)
    (mod_text_width 0.15)
    (pad_size 1.524 1.524)
    (pad_drill 0.762)
    (pad_to_mask_clearance 0.051)
    (solder_mask_min_width 0.25)
    (aux_axis_origin 0 0)
    (visible_elements 7FFFFFFF)
    (pcbplotparams
      (layerselection 0x010fc_ffffffff)
      (usegerberextensions false)
      (usegerberattributes false)
      (usegerberadvancedattributes false)
      (creategerberjobfile false)
      (excludeedgelayer true)
      (linewidth 0.100000)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (psnegative false)
      (psa4output false)
      (plotreference true)
      (plotvalue true)
      (plotinvisibletext false)
      (padsonsilk false)
      (subtractmaskfromsilk false)
      (outputformat 1)
      (mirror false)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory ""))
  )
  """
    kicad_str += '\n  '.join(kicad_nets)
    kicad_str += netclass_str
    kicad_str += '\n  '.join(kicad_module_strs)
    kicad_str += '\n'.join(zone_strings)
    kicad_str += '\n)'
    print(kicad_str)

    with open(arguments['<output_file>'], 'w') as f:
        f.write(kicad_str)


    print('#'*80)
    ordered = sorted(list(pin_counts.keys()), key=lambda x: pin_counts[x])
    for o in ordered:
        print(o, pin_counts[o])
    print('total nets: ' + str(len(node_types)))


if __name__ == "__main__":
    arguments = docopt(__doc__, version='DSN Parser 0.1')
    main(arguments)


