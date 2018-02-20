#!/bin/python3
import subprocess, argparse, shutil, time, sys, os
from math import ceil

# Config parameters. Time in seconds
################################################################################
sourcefile_path = "/opt/OpenFOAM/OpenFOAM-5.0/etc/bashrc"
location_in_mesh = "(0.1 0.1 0.1)" # C++ syntax
dispersion_time = 15
combustion_time = 15
logging = True
cores = 2


# Case setup
################################################################################
def run_case(create_mesh):

    # Initial Setup
    set_cores()
    clean("timeData", create_new=True)

    if create_mesh:
        clean("mesh", create_new=True)
        # Meshing with SnappyHexMesh
        shutil.copytree("snappyHexMesh/constant", "timeData/constant")
        shutil.copytree("snappyHexMesh/system", "timeData/system")
        change_line("timeData/system/snappyHexMeshDict", "locationInMesh", location_in_mesh)
        foam_call("surfaceFeatureExtract")
        foam_call("blockMesh")
        # foam_call("decomposePar")
        #TODO fix paralell mesh copy
        foam_call("snappyHexMesh", parallel=False)
        # foam_call("reconstructParMesh")
        cur, nxt = get_timestamps()
        # shutil.copytree("timeData/{}/polyMesh".format(cur), "mesh/polyMesh")
        shutil.rmtree("timeData/constant")
        shutil.rmtree("timeData/system")

    # input("Gas?")

    # Simulate gas dispersion
    cur, nxt = get_timestamps()
    shutil.copytree("rhoReactingBuoyantFoam/0", "timeData/{}".format(nxt))
    shutil.copytree("timeData/{}/polyMesh".format(cur), "timeData/{}/polyMesh".format(nxt))
    shutil.copy("timeData/{}/pointLevel".format(cur), "timeData/{}/pointLevel".format(nxt))
    shutil.copy("timeData/{}/cellLevel".format(cur), "timeData/{}/cellLevel".format(nxt))
    shutil.copytree("rhoReactingBuoyantFoam/constant", "timeData/constant")
    shutil.copytree("rhoReactingBuoyantFoam/system", "timeData/system")

    # shutil.copytree("mesh/polyMesh", "timeData/constant/polyMesh")
    foam_call("rhoReactingBuoyantFoam", parallel=False)
    shutil.rmtree("timeData/system")
    shutil.rmtree("timeData/constant")

    # input("Xplosionz????")

    # Simulate gas combustion
    cur, nxt = get_timestamps()
    shutil.copytree("XiFoam/constant", "timeData/constant")
    shutil.copytree("XiFoam/system", "timeData/system")
    shutil.copytree("XiFoam/0", "timeData/{}".format(nxt))
    shutil.copy("timeData/{}/H2".format(cur), "timeData/{}/ft".format(nxt))
    # FoamConvert to ASCII before change_line
    change_line("timeData/{}/ft".format(nxt), "object", "ft")
    copy_fields(cur, nxt)
    foam_call("XiFoam", parallel=False)


    # Reconstruct timesteps
    # foam_call("reconstructPar")


# Case functions
################################################################################
def foam_call(cmd, parallel=False):
    prog = cmd
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
    print_log("Running {0}, continous output in {0}.log".format(prog))
    p.wait()
    m, s = divmod(time.time() - start_time, 60)
    h, m = divmod(m, 60)
    print_log("Finished {} in {:.0f}h {:.0f}m {:.0f}s".format(prog, h, m, s))
    fout.close()
    if p.returncode != 0:
        print_log("Error while executing {}, check logs...".format(prog))
        sys.exit(1)


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


def get_timestamps():
    "Sets next timestep to whole number + 1 from previous timestep"
    latest_time = "-1"
    for folder in os.listdir("timeData"):
        try:
            if float(folder) > float(latest_time):
                latest_time = folder
        except ValueError:
            pass
    return latest_time, int(ceil(float(latest_time) + 1))


def set_cores():
    "Sets correct core count in all decomposeParDict's"
    change_line("snappyHexMesh/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("rhoReactingBuoyantFoam/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("XiFoam/system/decomposeParDict", "numberOfSubdomains", cores)


def copy_fields(cur, nxt):
    "Copies common fields when changing solver"
    for field in ["alphat", "epsilon", "k", "nut", "p", "p_rgh", "T", "U"]:
        shutil.copy("timeData/{}/{}".format(cur, field), "timeData/{}/{}".format(nxt, field))



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pyGDAXS: Gas Dispersion And Xplosion Solver")
    parser.add_argument("-a", action="store_true",
        default=False, help="Run all: Clean, mesh and simulate")
    parser.add_argument("-s", action="store_true",
        default=False, help="Simulate dispersion and combustion")
    parser.add_argument("-c", action="store_true",
        default=False, help="Clean mesh and solution folders and logs")
    parser.add_argument("-m", action="store_true",
        default=False, help="Generate new mesh. Not necessary for each new run")

    args = parser.parse_args()
    if args.a:
        args.c = True
        args.s = True
        args.m = True


    if args.c:
        print("Cleaning logfiles and solutions...")
        clean("timeData", create_new=False)
        clean("mesh", create_new=False)
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


    if args.s:
        run_case(args.m)
