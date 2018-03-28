#!/usr/bin/env python3
import subprocess, argparse, shutil, time, sys, os
from math import ceil
import select

# Config parameters
################################################################################
# source_path   = "/opt/OpenFOAM/OpenFOAM-5.0/etc/bashrc"
source_path = "/opt/openfoam5/etc/bashrc"

# Path is relative to the main pyGDAXS folder.
geometry_path = "geometries/hme_container2.obj"

# Program params
mpi_options   = "--map-by core --bind-to core --report-bindings"
cores = 16
logging = True

# Default jet: 1m diameter and 1m long
# Base at (0 0 0), pointing in z-direction
# Scaling occurs before rotation, un-even x&z scaling will flatten/widen
jet_scale = [0.4, 0.4, 0.4]

# Location of the base of jet geometry
# jet_location = [1, 1, 0.5]
jet_location = [100, 100, 100]

# Rotation [pitch, yaw] / rotation around [x-axis, y-axis] in degrees
# x-axis = 90 -> downward, x-axis = 270 -> upward
# Roll not included, as the jet is symmetric
jet_direction = [90, 0]

# Location of ignition source, must be inside mesh (not geometry)
ignition_location = [1.9, 1.9, 3]

# Solver run-time in seconds
dispersion_time = 6
combustion_time = 1



# Case setup
################################################################################
def run_case(create_mesh, simulate_dispersion, simulate_explosion):

    # Initial Setup
    clean_folder("timeData", create_new=True)
    in_mesh = "({} {} {})".format(*ignition_location)

    if create_mesh:
        print_log(
        """---------------------------------\
        \nMeshing phase                   |\
        \n---------------------------------""")
        clean_folder("save", create_new=True)
        copy_case_files("snappyHexMesh")
        change_line("timeData/system/snappyHexMeshDict", "locationInMesh", in_mesh)
        shutil.copy(geometry_path, "timeData/constant/triSurface/container.obj")
        # shutil.copy(geometry_path, "timeData/constant/triSurface/container.stl")
        place_jet(jet_scale, jet_location, jet_direction)

        # foam_call("surfaceFeatureExtract")
        foam_call("blockMesh")
        foam_call("decomposePar")
        foam_call("snappyHexMesh", parallel=True)
        foam_call("reconstructParMesh")
        foam_call("checkMesh")
        shutil.copytree("timeData/2/polyMesh", "save/polyMesh")


    if simulate_dispersion:
        print_log(
        """---------------------------------\
        \nDispersion phase                |\
        \n---------------------------------""")
        clean_folder("timeData", create_new=True)
        clean_folder("save/dispersion", create_new=False)
        copy_case_files("rhoReactingBuoyantFoam")
        shutil.copytree("save/polyMesh", "timeData/constant/polyMesh")
        change_line("timeData/system/controlDict", "endTime  ", dispersion_time)

        foam_call("decomposePar")
        foam_call("rhoReactingBuoyantFoam", parallel=True)
        if not simulate_explosion: foam_call("reconstructPar")
        else: foam_call("reconstructPar -latestTime")

        change_line("timeData/system/controlDict", "writeFormat", "ascii")
        foam_call("foamFormatConvert -latestTime")
        shutil.copytree("timeData/{}".format(get_latest_time()), "save/dispersion")


    if simulate_explosion:
        print_log(
        """---------------------------------\
        \nCombustion phase                |\
        \n---------------------------------""")
        clean_folder("timeData", create_new=True)
        copy_case_files("XiFoam")
        shutil.copytree("save/polyMesh", "timeData/constant/polyMesh")
        change_line("timeData/constant/combustionProperties", "    location", in_mesh)
        change_line("timeData/system/controlDict", "endTime  ", combustion_time)

        copy_field("T", "Tu")
        copy_field("H2", "ft")
        copy_field("p_rgh", "p")
        copy_common_fields(["alphat", "epsilon", "k", "nut", "T", "U"])

        foam_call("decomposePar")
        foam_call("XiFoam", parallel=True)
        foam_call("reconstructPar")



# Case functions
################################################################################
def foam_call(cmd, parallel=False, last=True):
    prog = cmd.split(" ")[0]
    clean_file(".running_{}".format(prog), create_new=True)
    start_time = time.time()
    if logging:
        fout = open("log.{}".format(prog), "a")
    else:
        fout = open("/dev/null", "w")
    if parallel:
        cmd = "mpirun -np {} {} {} -parallel".format(cores, mpi_options, cmd)
    try:
        p = subprocess.Popen(
            "cd {} && source {} && {}".format("timeData", source_path, cmd),
            shell = True,
            executable = "/bin/bash",
            stdout = fout, stderr = fout
        )
        if logging:
            print("Running  {}".format(prog), end="\r")
        p.wait()
    except KeyboardInterrupt:
        print_log("\r{} canceled by user...".format(prog))
        sys.exit(0)
    m, s = divmod(time.time() - start_time, 60)
    h, m = divmod(m, 60)
    fout.close()
    if p.returncode != 0:
        print_log("Error while running {} after {:3.0f}h{:3.0f}m{:3.0f}s, check logs...".format(
            prog, h, m, s))
        clean_file(".running_{}".format(prog), create_new=False)
        sys.exit(1)
    if logging and last:
        print_log("Finished {:23}|{:3.0f}h{:3.0f}m{:3.0f}s".format(prog, h, m, s))
    clean_file(".running_{}".format(prog), create_new=False)


def print_log(line):
    if logging:
        with open("log.pyGDAXS", "a") as logfile:
            logfile.write(line)
            logfile.write("\n")
    print(line)


def clean_folder(path, create_new=True):
    if os.path.isdir(path):
        shutil.rmtree(path)
    if create_new:
        os.mkdir(path)


def clean_file(path, create_new=False):
    if os.path.isfile(path):
        os.remove(path)
    if create_new:
        with open(path, "w") as of:
            of.write("Running...")


def change_line(path, key, value):
    "Changes the first value in the given file to the specifies value"
    new_content = []
    with open(path, "r") as infile:
        lines = infile.readlines()

    for line in lines:
        if key in line:
            new_content.append("{}       {};\n".format(key, value))
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


def copy_case_files(case):
    shutil.copytree("{}/system".format(case), "timeData/system")
    shutil.copytree("{}/constant".format(case), "timeData/constant")
    change_line("timeData/system/decomposeParDict", "numberOfSubdomains", cores)
    if case != "snappyHexMesh":
        shutil.copytree("{}/0".format(case), "timeData/0")


def copy_field(a, b):
    "Copies common fields when changing from dispersion to combustion solver"
    shutil.copy("save/dispersion/{}".format(a),"timeData/0/{}".format(b))
    change_line("timeData/0/{}".format(b), "object", b)
    change_line("timeData/0/{}".format(b), "location", "0")


def copy_common_fields(fields):
    for f in fields:
        shutil.copy("save/dispersion/{}".format(f), "timeData/0/{}".format(f))
        change_line("timeData/0/{}".format(f), "location", "0")


def place_jet(s, l, d):
    stp = "surfaceTransformPoints"
    start_time = time.time()

    for patch in ["base", "inlet"]:
        obj = "constant/triSurface/{}.obj".format(patch)
        shutil.copy("snappyHexMesh/jetSurfaces/{}.obj".format(patch),
            "timeData/{}".format(obj))

        foam_call("{0} -scale '({1} {2} {3})' {4} {4}".format(
            stp, s[0], s[1], s[2], obj), last = False)
        foam_call("{0} -rollPitchYaw '({1} {2} 0)' {3} {3}".format(
            stp, d[0], d[1], obj), last = False)
        foam_call("{0} -translate '({1} {2} {3})' {4} {4}".format(
            stp, l[0], l[1], l[2], obj), last = False)

    m, s = divmod(time.time() - start_time, 60)
    h, m = divmod(m, 60)
    print_log("Finished {:23}|{:3.0f}h{:3.0f}m{:3.0f}s".format(stp, h, m, s))


def set_run(args, state):
    args.c = state
    args.m = state
    args.d = state
    args.x = state



if __name__ == "__main__":
    pars = argparse.ArgumentParser(description="pyGDAXS: Gas Dispersion And Xplosion Solver")
    excl = pars.add_mutually_exclusive_group()
    pars.add_argument("-a", action="store_true",
        default=False, help="Run all: Clean, generate mesh and simulate")
    pars.add_argument("-m", action="store_true",
        default=False, help="Generate new mesh")
    pars.add_argument("-d", action="store_true",
        default=False, help="Simulate gas dispersion, requires mesh")
    pars.add_argument("-x", action="store_true",
        default=False, help="Simulate gas explosion, requires mesh & dispersion")
    pars.add_argument("-c", action="store_true",
        default=False, help="Clean mesh and solution folders and logs")
    excl.add_argument("--info", action="store_true",
        default=False, help="Continuously print courant number and time data.\
        Requires a running simulation")


    args = pars.parse_args()
    print_log("\n")

    if args.info:
        if os.path.isfile(".running_rhoReactingBuoyantFoam"):
            lf = "rhoReactingBuoyantFoam"
        elif os.path.isfile(".running_XiFoam"):
            lf = "XiFoam"
        else:
            print("No running simulations found...")
            sys.exit(0)

        f = subprocess.Popen(
            "tail -fn 200 log.{} | grep -E 'Courant Number mean|deltaT|Time = '".format(lf),
            shell = True,
            executable = "/bin/bash",
            stdout=None,
            stderr=None
        )
        while os.path.isfile(".running_{}".format(lf)):
            time.sleep(5)
        f.terminate()


    if args.a:
        set_run(args, True)


    if args.c:
        print_log("---------------------------------")
        print_log("Cleaning logfiles and solutions |")
        clean_file("log.pyGDAXS")
        clean_folder("timeData", create_new=False)
        clean_folder("save", create_new=False)
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


    if not args.d and not os.path.isdir("save/dispersion") and args.x:
        yn = input("No dispersion data found, Create now?  (y/n)\n")
        if yn in ["Y", "y"]:
            args.d = True
        else:
            set_run(args, False)

    if not args.m and not os.path.isdir("save/polyMesh") and args.d:
        yn = input("No mesh created, Create now?  (y/n)\n")
        if yn in ["Y", "y"]:
            args.m = True
        else:
            set_run(args, False)



    if any([args.m, args.d, args.x]):
        run_case(args.m, args.d, args.x)
