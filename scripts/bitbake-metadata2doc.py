#! /usr/bin/env python

import os
import sys
import pickle

def info(fmt, *args):
    print(fmt % args)

def tabularize(lines, spacing=2):
    def format_border(widths):
        return spc.join([ '=' * width for width in widths ])

    def format_header(header, widths, spc):
        border = format_border(widths)
        header = spc.join(map(lambda col, width: col.ljust(width),
                              header, widths))
        return '\n'.join([border, header, border])

    def sort_by_col(lines, col):
        return sorted(lines, key=lambda l: l[col])

    def format_body(lines, widths, spc):
        def format_line (line):
            return spc.join(map(lambda col, width: col.ljust(width),
                                line, widths))
        return "\n".join(map(format_line, sort_by_col(lines, 0)))

    spc = ' ' * spacing
    if lines:
        col_widths = map(lambda col: apply(max, map(len, col)),
                         apply(zip, lines))
        return '\n'.join([format_header(lines[0], col_widths, spc),
                          format_body(lines[1:], col_widths, spc),
                          format_border(col_widths)]) + \
               '\n'
    else:
        return ""

def describe(items):
    text = ''
    for item in items:
        text += ''.join(['* ', '**', item[0], '**: ', item[1], '\n'])
    return text

def write_inc_file(file, text):
    out_file = os.path.join(out_dir, file)
    info('Writing %s' % out_file)
    out_fd = open(out_file, 'w')
    out_fd.write(text)
    out_fd.close()

def write_tabular(file, header, body):
    table = [header] + body
    write_inc_file(file, tabularize([header] + body))

def write_table_by_recipe(file, recipe, header, data):
    body = []
    for board in data.keys():
        recipe_data = data[board]['recipes'][recipe]
        body += [[board, recipe_data['recipe'], recipe_data['version']]]
    write_tabular(file, header, body)

def write_linux_table(data, out_dir):
    write_table_by_recipe('linux-default.inc',
                          'virtual/kernel',
                          ['Board', 'Kernel Provider', 'Kernel Version'],
                          data)

def write_u_boot_table(data, out_dir):
    write_table_by_recipe('u-boot-default.inc',
                          'virtual/bootloader',
                          ['Board', 'U-Boot Provider', 'U-Boot Version'],
                          data)

def write_barebox_table(data, out_dir):
    boards = filter(lambda board: data[board]['recipes'].has_key('barebox'), data.keys())
    boards_data = {}
    for board in boards:
        boards_data[board] = data[board]
    write_table_by_recipe('barebox-mainline.inc',
                          'barebox',
                          ['Board', 'Barebox Provider', 'Barebox Version'],
                          boards_data)

def write_fsl_community_bsp_supported_kernels(data, out_dir):
    kernels = []
    kernel_recipes = [] # just to keep track of recipes already collected
    for board, board_data in data.items():
        kernel = board_data['recipes']['virtual/kernel']
        recipe = kernel['recipe']
        if (kernel['layer'] in ['meta-fsl-arm', 'meta-fsl-arm-extra']) and \
            recipe not in kernel_recipes:
            kernels += [[recipe, kernel['description']]]
            kernel_recipes.append(recipe)
    write_inc_file('fsl_community_bsp_supported_kernels.inc', describe(kernels))

def usage(exit_code=None):
    print 'Usage: %s <data file> <output dir>' % (os.path.basename(sys.argv[0]),)
    if exit_code:
        sys.exit(exit_code)



if '-h' in sys.argv or '-help' in sys.argv or '--help' in sys.argv:
    usage(0)

if len(sys.argv) < 2:
    usage(1)

data_file = sys.argv[1]
out_dir = sys.argv[2]

data_fd = open(data_file, 'r')
data = pickle.load(data_fd)
data_fd.close()

try:
    os.mkdir(out_dir)
except:
    if not os.path.isdir(out_dir):
        sys.stderr.write('A file named %s already exists. Aborting.' % out_dir)
        sys.exit(1)
    else:
        pass # if a directory already exists, it's ok

write_linux_table(data, out_dir)
write_u_boot_table(data, out_dir)
write_barebox_table(data, out_dir)
write_fsl_community_bsp_supported_kernels(data, out_dir)
