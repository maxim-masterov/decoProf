import subprocess
import time
import sys
import argparse
import json
import os
import shutil
import ast
import astunparse


def print_msg_with_header(msg_header, msg):
    """
    Print a message with a header to terminal
    :param msg_header: Header of the message
    :param msg: Message body
    :return: None
    """
    print(msg_header, end=' ')
    print(msg)


def print_dbg_info(msg):
    """
    Print a debug message to terminal
    :param msg: Message body
    :return: None
    """
    msg_header = "== DEBUG =="
    if __debug__:
        print_msg_with_header(msg_header, msg)


def print_err_info(msg):
    """
    Print an error message to terminal
    :param msg: Message body
    :return: None
    """
    msg_header = "== ERROR =="
    print_msg_with_header(msg_header, msg)


def generate_call_tree(args, working_dir_name):
    """
    Generate a call tree using PyCG package (see https://github.com/vitsalis/PyCG).
    PyCG is called using a subprocess and generates a JSON file as a result of its execution
    :param args: List of CLI arguments passed to this script
    :param working_dir_name: Name of the working directory where JSON file will be stored. It's
                             also used as a basename for the JSON file
    :return: Output filename
    """
    # Assemble unique output filename
    output_filename = working_dir_name + '/' + working_dir_name + '.json'
    print_dbg_info('Output filename: \t' + output_filename)

    # Execute PyCG
    subprocess.run(['pycg', '--package', str(args.p), str(args.p) + '/' + str(args.f),
                    '-o', output_filename])

    return output_filename


def read_call_tree(filename):
    """
    Read the call tree from a file
    :param filename: Filename
    :return: Dictionary of a call tree
    """
    call_tree = None
    with open(filename) as json_file:
        call_tree = json.load(json_file)
    return call_tree


def check_arg_existence(arg, arg_name, parser):
    """
    Check existence of a mandatory argument. Throw an error and exit if argument
    is not specified
    :param arg: Argument to be checked
    :param arg_name: Argument's meta name
    :param parser: Parser object
    :return: None
    """
    if arg is None:
        print_err_info(arg_name + ' is not specified.')
        parser.print_help()
        exit(1)


def parse_cli():
    """
    Parse CLI arguments passed to this script and check for their correctness.
    :return: Object of parsed arguments.
    """
    # Instantiate the parser
    args = None
    parser = argparse.ArgumentParser(prog='ctg', usage='%(prog)s [options]',
                                     description='Create call tree.')
    parser.add_argument('-f', metavar='<filename>', type=str,
                        help='Specify the file name.')
    parser.add_argument('-p', metavar='<project name>', type=str,
                        help='Specify the project name.')
    parser.add_argument('-n', metavar='<function name>', type=str,
                        help='Function name to be analyzed.')

    # Check if we have enough arguments, otherwise print error message and help
    if len(sys.argv) > 1:
        args = parser.parse_args()

        # All CLI arguments are mandatory
        check_arg_existence(args.f, 'Filename', parser)
        check_arg_existence(args.p, 'Project name', parser)
        check_arg_existence(args.n, 'Function name', parser)

        # Print some debug info
        print_dbg_info('Filename: \t' + str(args.f))
        print_dbg_info('Project name: \t' + str(args.p))
        print_dbg_info('Function name: \t' + str(args.n))
    else:
        print_err_info('No CLI arguments passed.')
        parser.print_help()
        exit(1)

    return args


def append_decorator_to_tree(node, function_name, decorator_name):
    """
    Append decorator to the AST's structure
    :param node: Node which should contain the function
    :param function_name: Function name to which we should add decorator to
    :param decorator_name: Name of the decorator
    :return: None
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef):
            if child.name == function_name:
                print_dbg_info('function_name: ' + child.name)
                print_dbg_info('original decorator_list: ')
                print_dbg_info(child.decorator_list)

                child.decorator_list.append(ast.Name(id=decorator_name, ctx=ast.Load()))

                print_dbg_info('modified decorator_list: ')
                print_dbg_info(child.decorator_list)


def inject_decorator(src_tree, function_name, decorator_name):
    """
    Inject decorator to the AST
    :param src_tree: AST
    :param function_name: Function name to which the decorator should be added to
    :param decorator_name: Name of the decorator that should be injected
    :return: None
    """
    # function_to_be_changed = 'check_size'
    pattern_names = str(function_name).split('.')

    is_class = False
    if len(pattern_names) > 1:
        is_class = True
        print_dbg_info('Function "' + function_name + '" is a member of a class')
    else:
        print_dbg_info('Function "' + function_name + '" is not a member of a class')

    # decorator_name = 'test'

    print_dbg_info(ast.dump(src_tree))
    for node in ast.walk(src_tree):
        if is_class:
            if isinstance(node, ast.ClassDef) and node.name == pattern_names[0]:
                append_decorator_to_tree(node, pattern_names[1], decorator_name)
        else:
            append_decorator_to_tree(node, pattern_names[0], decorator_name)

    # print_dbg_info(ast.dump(src_tree))
    #
    # print_dbg_info('Modified code:')
    # print_dbg_info(astunparse.unparse(src_tree))


def inject_import(src_tree, module_name, class_name):
    """
    Inject "import" statement at the beginning of the source file
    :param src_tree: AST
    :param module_name: Module to be imported
    :param class_name: Class name from the 'module_name'
    :return: None
    """
    import_node = ast.ImportFrom(module=module_name, names=[ast.alias(name=class_name, asname='gp')], level=0)
    src_tree.body.insert(0, import_node)


def parse_src_file(filename):
    """
    Parse source file to build AST
    :param filename: Filename
    :return: AST object
    """
    file = open(filename, 'r')
    code = file.read()
    file.close()

    src_tree = ast.parse(code)

    return src_tree


def create_tmp_dir(args):
    """
    Create temporary directory
    :param args: List of CLI arguments
    :return: Name of the created directory
    """
    timestamp = str(time.time()).replace('.', '')
    dir_name = str(args.p) + "_" + timestamp

    print_dbg_info('Creating temporary directory: ' + dir_name)
    os.mkdir(dir_name)

    return dir_name


def make_working_copy_of_src(src_dir_name, dst_dir_name):
    """
    Copy source files to the working directory
    :param src_dir_name: Path to the directory with source files
    :param dst_dir_name: Path to the working directory
    :return: None
    """
    print_dbg_info('Copying sources to the temporary directory: ' + src_dir_name + ' --> ' + dst_dir_name)
    shutil.copytree('./' + src_dir_name, './' + dst_dir_name, dirs_exist_ok=True)


def dump_decorated_src(src_tree, working_copy_filename):
    """
    Write AST to the file
    :param src_tree: AST object
    :param working_copy_filename: Filename AST should be written into
    :return: None
    """
    file = open(working_copy_filename, 'w')
    file.write(astunparse.unparse(src_tree))
    file.close()


def main(decorator_name, module_name, module_class_name):
    """
    1) Analyze CLI arguments
    2) Generate a call tree
    :param decorator_name: Name of the decorator that should be injected
    :param module_name: Name of the module that should be added to the "import"
                        statement at the header of the script
    :param module_class_name: Name of the class from the "module_name"
    :return: None
    """
    # parse CLI arguments
    args = parse_cli()

    print_msg_with_header('', '--------------------')
    print_msg_with_header('', 'Starting decorator injector...')

    # Create a temporary directory
    working_dir_name = create_tmp_dir(args)

    # Make a working copy of the scripts we are going to work with
    make_working_copy_of_src(args.p, working_dir_name)

    # Run call tree generator
    call_tree_filename = generate_call_tree(args, working_dir_name)
    call_tree = read_call_tree(call_tree_filename)

    # Run AST
    working_copy_filename = working_dir_name + '/' + os.path.basename(args.f)
    print_dbg_info(working_copy_filename)
    src_tree = parse_src_file(working_copy_filename)

    # Inject decorator into the source code
    inject_decorator(src_tree, args.n, decorator_name)

    # Inject "import"
    inject_import(src_tree, module_name, module_class_name)

    print_dbg_info('Modified code:')
    print_dbg_info(astunparse.unparse(src_tree))

    # Write modified tree back into the file
    dump_decorated_src(src_tree, working_copy_filename)

    print_msg_with_header('', '--------------------')
    print_msg_with_header('', 'Done!')


if __name__ == '__main__':
    """
    User should specify a function name including the class name the function belongs 
    to, e.g.:
        class Vector:
            def __init__():
                ...
            def add():
                ...
    User input: -f vector.py -n Vector.add 
    """

    print_msg_with_header('', '')

    # example: python3 main.py -f factorial.py -p examples -n benchmark
    # TODO:
    #  - make it work for functions with an arbitrary number of arguments
    profiler_decorator_name = 'gp.cprofile_decorator'
    profiler_module_name = 'genericProfiler'
    profiler_class_name = 'ProfileDecorators'
    main(profiler_decorator_name, profiler_module_name, profiler_class_name)