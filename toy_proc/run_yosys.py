#!/usr/bin/env python3
"""
helper tool to run yosys, generating appropriate yosys script
python, rather than bash, since commandline arguments etc
so much more convenenient in python

In addiition, we can give a task, by providing --top-task [task name].
The task should be the only declaration, in a file with the exact same name.
ports should be provided one per line, without nothing else on the line except the trailing commma (',').

run_yosys.py will wrap the task in a module, then synthesize that.

Any comments prior to the declaration should only use // for now (not /* */). And these comments should be at
the beginning of the line.

there should be a space before each port name in the task declaration.

PRs to improve this welcome :)

No comments allowed in the task declaration itself.
"""
import argparse
import os
from collections import deque


"""
For reference, example of task and module wrapper for it:

task prot_task(
    input [1:0] a,
    input [1:0] b,
    output reg [1:0] out
);
    out = a + b;
endtask

module prot_task_module(
    input [1:0] a,
    input [1:0] b,
    output reg [1:0] out
);
    always @(*) begin
        prot_task(a, b, out);
    end
endmodule
"""


def run(args):
    if args.top_task is not None:
        task_verilog_files = [n for n in args.in_verilog if n.endswith(f'/{args.top_task}.sv')]
        assert len(task_verilog_files) == 1
        task_verilog_file = task_verilog_files[0]
        print('task verilog file', task_verilog_file)
        with open(task_verilog_file) as f:
            task_contents = f.read()
        port_declarations = []  # full declaration, e.g. "input [1:0] a"
        port_names = []  # just the name, e.g. "a"
        in_declaration = False
        for line in task_contents.split('\n'):
            line = line.strip()
            if line.startswith('//'):
                continue
            if line.startswith('task'):
                in_declaration = True
                continue
            if in_declaration:
                if line == ');':
                    break
                port_declaration = line
                if port_declaration.endswith(','):
                    port_declaration = port_declaration[:-1]
                port_declarations.append(port_declaration)
                name = port_declaration.split()[-1]
                port_names.append(name)
        print('declarations', port_declarations)
        print('names', port_names)
        wrapper_filepath = 'build/task_wrapper.sv'
        args.in_verilog.append(wrapper_filepath)
        args.top_module = f'{args.top_task}_module'
        with open(wrapper_filepath, 'w') as f:
            port_declarations_str = ',\n    '.join(port_declarations)
            port_names_str = ', '.join(port_names)
            f.write(f"""module {args.top_task}_module(
    {port_declarations_str}
);
    always @(*) begin
        {args.top_task}({port_names_str});
    end
endmodule
""")
        os.system(f"cat {wrapper_filepath}")

    with open('build/yosys.tcl', 'w') as f:
        for file in args.in_verilog:
            f.write(f"read_verilog -sv {file}\n")
        if not os.path.exists('build/netlist'):
            os.makedirs('build/netlist')
        if args.top_module:
            f.write(f'hierarchy -top {args.top_module}')
        f.write(f"""
delete t:$assert
write_verilog build/netlist/0.v
flatten
write_verilog build/netlist/1.v
synth
write_verilog build/netlist/2.v
techmap;
write_verilog build/netlist/3.v
# ltp
dfflibmap -liberty {args.cell_lib}
write_verilog build/netlist/4.v
abc -liberty {args.cell_lib}
""")
        if not args.no_cells:
            f.write("""
write_verilog build/netlist/5.v
clean
write_verilog build/netlist/6.v
""")
        f.write("""
write_rtlil build/rtlil.rtl
write_verilog build/netlist.v
ltp
sta
stat
""")
        if args.show:
            f.write('show\n')
    if os.system('yosys -s build/yosys.tcl') != 0:
        raise Exception("Failed")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--top-task', type=str,
        help='give this instead of top module if it\'s a task. Should match filename')
    parser.add_argument('--in-verilog', type=str, nargs='+', required=True, help='path to verilog file')
    parser.add_argument(
        '--top-module', type=str, help='top module name, only needed if more than one module.')
    parser.add_argument('--show', action='store_true', help='show xdot on the result')
    parser.add_argument('--no-cells', action='store_true', help='stop after dfflibmap')
    parser.add_argument(
        '--cell-lib', type=str, default='tech/osu018/osu018_stdcells.lib',
        help='e.g. path to osu018_stdcells.lib')
    args = parser.parse_args()
    args.in_verilog = deque(args.in_verilog)
    for additional in ['src/assert_ignore.sv', 'src/op_const.sv', 'src/const.sv']:
        if additional not in args.in_verilog:
            args.in_verilog.appendleft(additional)
    print(args.in_verilog)

    run(args)
