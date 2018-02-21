#!/bin/python3
import subprocess, argparse, shutil, time, sys, os
from math import ceil

# Config parameters. Time in seconds
################################################################################
sourcefile_path = "/opt/OpenFOAM/OpenFOAM-5.0/etc/bashrc"
ignition_location = "(0.7 1.8 1.0)" # C++ syntax
dispersion_time = 10
combustion_time = 1
logging = True
cores = 2


# Case setup
################################################################################
def run_case(create_mesh, simulate_dispersion, simulate_explosion):

    # Initial Setup
    set_cores()
    clean("timeData", create_new=True)

    # Meshing with SnappyHexMesh
    if create_mesh:
        clean("save", create_new=True)
        shutil.copytree("snappyHexMesh/system", "timeData/system")
        shutil.copytree("snappyHexMesh/constant", "timeData/constant")
        change_line("timeData/system/snappyHexMeshDict", "locationInMesh", ignition_location)

        foam_call("surfaceFeatureExtract")
        foam_call("blockMesh")
        foam_call("decomposePar")
        foam_call("snappyHexMesh", parallel=True)
        foam_call("reconstructParMesh")
        shutil.copytree("timeData/constant/polyMesh", "save/polyMesh")


    # Simulate gas dispersion
    if simulate_dispersion:
        clean("timeData", create_new=True)
        shutil.copytree("rhoReactingBuoyantFoam/constant", "timeData/constant")
        shutil.copytree("rhoReactingBuoyantFoam/system", "timeData/system")
        shutil.copytree("save/polyMesh", "timeData/constant/polyMesh")
        shutil.copytree("rhoReactingBuoyantFoam/0", "timeData/0")
        change_line("timeData/system/controlDict", "endTime  ", dispersion_time)

        foam_call("decomposePar")
        foam_call("rhoReactingBuoyantFoam", parallel=True)
        foam_call("reconstructPar -latestTime")
        shutil.copytree("timeData/{}".format(get_latest_time()), "save/dispersion")


    # Simulate gas combustion
    if simulate_explosion:
        clean("timeData", create_new=True)
        shutil.copytree("XiFoam/0", "timeData/0")
        shutil.copytree("XiFoam/system", "timeData/system")
        shutil.copytree("XiFoam/constant", "timeData/constant")
        shutil.copytree("save/polyMesh", "timeData/constant/polyMesh")
        change_line("timeData/constant/combustionProperties", "    location", ignition_location)
        change_line("timeData/system/controlDict", "endTime  ", combustion_time)
        copy_field("T", "Tu")
        copy_field("H2", "ft")
        copy_field("p_rgh", "p")
        copy_common_fields()

        foam_call("decomposePar")
        foam_call("XiFoam", parallel=True)
        foam_call("reconstructPar")



# Case functions
################################################################################
def foam_call(cmd, parallel=False):
    prog = cmd.split(" ")[0]
    start_time = time.time()
    fout = open("log.{}".format(prog), "w")
    if parallel: cmd = "mpirun -np {} {} -parallel".format(cores, cmd)
    p = subprocess.Popen(
        "cd {} && source {} && {}".format("timeData", sourcefile_path, cmd),
        shell = True,
        executable = "/bin/bash",
        stdout = fout if logging else None,
        stderr = fout if logging else None,
    )
    print("Running  {}".format(prog), end="\r")
    p.wait()
    m, s = divmod(time.time() - start_time, 60)
    h, m = divmod(m, 60)
    fout.close()
    if p.returncode != 0:
        print_log("Error while executing {}, check logs...".format(prog))
        sys.exit(1)
    print_log("Finished {:22}: {:.0f}h {:.0f}m {:.0f}s".format(prog, h, m, s))




def print_log(line):
    if logging:
        with open("log.pyGDAXS", "a") as logfile:
            logfile.write(line)
            logfile.write("\n")
    print(line)


def clean(folder, create_new=True):
    if os.path.isdir(folder):
        shutil.rmtree(folder)
        if create_new:
            os.mkdir(folder)
    else:
        if create_new:
            os.mkdir(folder)


def change_line(path, key, value):
    "Changes the value in the given file to the specifies value"
    new_content = []
    with open(path, "r") as infile:
        lines = infile.readlines()

    for line in lines:
        if key in line:
            new_content.append("{}      {};\n".format(key, value))
        else:
            new_content.append(line)

    with open(path, "w") as outfile:
        outfile.writelines(new_content)


def get_latest_time():
    "Sets next timestep to whole number + 1 from previous timestep"
    latest_time = "0"
    for folder in os.listdir("timeData"):
        try:
            if float(folder) > float(latest_time):
                latest_time = folder
        except ValueError:
            pass
    return latest_time


def set_cores():
    "Sets correct core count in all decomposeParDict's"
    change_line("snappyHexMesh/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("rhoReactingBuoyantFoam/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("XiFoam/system/decomposeParDict", "numberOfSubdomains", cores)


def copy_field(a, b):
    "Copies common fields when changing from dispersion to combustion solver"
    shutil.copy("save/dispersion/{}".format(a),"timeData/0/{}".format(b))
    change_line("timeData/0/{}".format(b), "object", b)

def copy_common_fields():
    # for field in os.listdir("save/dispersion"):
    for f in ["alphat", "epsilon", "k", "nut", "T", "U"]:
        shutil.copy("save/dispersion/{}".format(f), "timeData/0/{}".format(f))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pyGDAXS: Gas Dispersion And Xplosion Solver")
    parser.add_argument("-a", action="store_true",
        default=False, help="Run all: Clean, mesh and simulate")
    parser.add_argument("-d", action="store_true",
        default=False, help="Simulate gas dispersion")
    parser.add_argument("-x", action="store_true",
        default=False, help="Simulate gas explosion")
    parser.add_argument("-c", action="store_true",
        default=False, help="Clean mesh and solution folders and logs")
    parser.add_argument("-m", action="store_true",
        default=False, help="Generate new mesh. Not necessary for each new run")

    args = parser.parse_args()
    if args.a:
        args.c = True
        args.m = True
        args.d = True
        args.x = True


    if args.c:
        print("Cleaning logfiles and solutions...")
        clean("timeData", create_new=False)
        clean("save", create_new=False)
        del_files = ["log.", ".eMesh"]
        del_folders = ["polyMesh", "extendedFeatureEdgeMesh", "processor"]
        for dirpath, dnames, fnames in os.walk("./"):
            for f in fnames:
                for df in del_files:
                    if df in f:
                        os.remove(os.path.join(dirpath,f))
            for d in dnames:
                if ".git" not in dirpath and d != "0":
                    for df in del_folders:
                        if df in d:
                            shutil.rmtree(os.path.join(dirpath,d))
                    try:
                        f = float(d)
                        shutil.rmtree(os.path.join(dirpath,d))
                    except ValueError:
                        pass


    if any([args.m, args.d, args.x]):
        run_case(args.m, args.d, args.x)
