#!/bin/python3
import subprocess, argparse, shutil, time, sys, os
from math import ceil

# Configs
################################################################################
sourcefile_path = "/opt/OpenFOAM/OpenFOAM-5.0/etc/bashrc"
logging = True
cores = 4


# Case setup
################################################################################
def run_case():

    # Initial Setup
    set_cores()
    clean("timeData")
    clean("tmp")


    # Meshing with SnappyHexMesh
    shutil.copytree("snappyHexMesh/constant", "timeData/constant")
    shutil.copytree("snappyHexMesh/system", "timeData/system")
    foam_call("blockMesh")
    foam_call("decomposePar")
    foam_call("snappyHexMesh", parallel=True)
    # reconstructParMesh ?
    shutil.move("timeData/constant/ployMesh", "tmp/ployMesh")
    shutil.rmtree("timeData/constant")
    shutil.rmtree("timeData/system")


    # Simulate gas dispersion
    shutil.copytree("rhoReactingBuoyantFoam/constant", "timeData/constant")
    shutil.copytree("rhoReactingBuoyantFoam/system", "timeData/system")
    shutil.move("tmp/polyMesh", "timeData/constant/polyMesh")
    foam_call("rhoReactingBuoyantFoam", parallel=True)
    shutil.rmtree("timeData/constant")
    shutil.rmtree("timeData/system")


    # Simulate gas combustion
    cur, nxt = get_timestamps()
    shutil.copytree("XiFoam/constant", "timeData/constants")
    shutil.copytree("XiFoam/system", "timeData/system")
    shutil.copytree("XiFoam/0", "timeData/{}".format(nxt))
    shutil.copy("{}/H2".format(cur), "{}/ft".format(nxt))
    change_line("{}/ft".format(nxt), "object", "ft")
    copy_fields(cur, nxt)
    foam_call("XiFoam", parallel=True)


    # Reconstruct timesteps
    foam_call("reconstructPar")
    shutil.rmtree("tmp")


# Case functions
################################################################################
def foam_call(cmd, parallel=False):
    start_time = time.time()
    fout = open("log.{}".format(cmd), "w")
    if parallel: cmd = "mpirun -np {} {} -parallel".format(cores, cmd)
    p = subprocess.Popen(
        "cd {} && source {} && {}".format("timeData", sourcefile_path, cmd),
        shell = True,
        executable = "/bin/bash",
        stdout = fout if logging else None,
        stderr = fout if logging else None,
    )
    print_log("Running {0}, continous output in {0}.log".format(cmd))
    p.wait()
    m, s = divmod(time.time() - start_time, 60)
    h, m = divmod(m, 60)
    print_log("Finished {} in {:.0f}h {:.0f}m {:.0f}s".format(cmd, h, m, s))
    fout.close()
    return p.returncode


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
    latest_time = -1
    for folder in os.listdir(path):
        try:
            float(s)
            if s > latest_time:
                latest_time = s
        except ValueError:
            pass
    return latest_time, int(ceil(latest_time + 1))


def set_cores():
    "Sets correct core count in all decomposeParDict's"
    change_line("snappyHexMesh/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("rhoReactingBuoyantFoam/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("XiFoam/system/decomposeParDict", "numberOfSubdomains", cores)


def copy_fields(cur, nxt):
    "Copies common fields when changing solver"
    for field in ["alphat", "epsilon", "k", "nut", "p", "p_rgh", "T", "U"]:
        shutil.move("{}/{}".format(cur, field), "{}/{}".format(nxt, field))



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pyGDAXS: Gas Dispersion And Xplosion Solver")
    parser.add_argument("--run", action="store_true",
                        default=False, help="Run the complete simulation")

    parser.add_argument("--clean", action="store_true",
                        default=False, help="Run the complete simulation")

    args = parser.parse_args()

    if args.clean:
        print("Cleaning logfiles and solutions...")
        clean("timeData", create_new=False)
        clean("tmp", create_new=False)
        del_files = ["log.", ".eMesh"]
        del_folders = ["polyMesh", "extendedFeatureEdgeMesh"]
        for dirpath, dnames, fnames in os.walk("./"):
            for f in fnames:
                for df in del_files:
                    if df in f:
                        os.remove(os.path.join(dirpath,f))
            for d in dnames:
                for df in del_folders:
                    if df in d:
                        shutil.remdir(os.path.join(dirpath,d))

    if args.run:
        run_case()
