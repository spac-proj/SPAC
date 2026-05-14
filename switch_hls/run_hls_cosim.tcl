# commands to run:
# source /mnt/ccnas2/bdp/opt/Xilinx/Vitis/2022.1/settings64.sh
# vitis_hls -i 
# vitis_hls -f run_hls_cosim.tcl

open_project -reset CustomSwitch_prj
set_top switch_top
add_files ./CustomSwitch/code/src/hash_engine.cpp -cflags "-I./CustomSwitch/code/include"
add_files ./CustomSwitch/code/src/rx_engine.cpp -cflags "-I./CustomSwitch/code/include"
add_files ./CustomSwitch/code/src/scheduler.cpp -cflags "-I./CustomSwitch/code/include"
add_files ./CustomSwitch/code/src/scheduler_nb1p.cpp -cflags "-I./CustomSwitch/code/include"
add_files ./CustomSwitch/code/src/switch_top.cpp -cflags "-I./CustomSwitch/code/include"
add_files -tb ./CustomSwitch/code/tests/simple_tb.cpp -cflags "-I./CustomSwitch/code/include"
open_solution "solution32"
set_part {xcu26-vsva1365-2LV-e}
create_clock -period 10 -name default
csynth_design
cosim_design -rtl verilog -tool auto -trace_level all
exit