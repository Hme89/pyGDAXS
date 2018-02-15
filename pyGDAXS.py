import subprocess, shutil, time, sys, os
from math import ceil

################################################################################

sourcefile_path = "/opt/OpenFOAM/OpenFOAM-5.0/etc/bashrc"
logging = True
cores = 4

################################################################################

def run_case():

    # Initial Setup
    set_cores()
    clean("timeData")
    clean("tmp")


    # Meshing with SnappyHexMesh
    shutil.copytree("snappyHexMesh/constant", "timeData")
    shutil.copytree("snappyHexMesh/system", "timeData")
    foam_call("blockMesh")
    foam_call("decomposePar")
    foam_call("snappyHexMesh", parallel=True)
    # reconstructParMesh ?
    shutil.move("timeData/constant/ployMesh", "tmp")
    shutil.rmtree("timeData/constant")
    shutil.rmtree("timeData/system")


    # Simulate gas dispersion
    shutil.copytree("rhoReactingBuoyantFoam/constant", "timeData")
    shutil.copytree("rhoReactingBuoyantFoam/system", "timeData")
    shutil.move("tmp/polymesh", "timeData/constant")
    foam_call("rhoReactingBuoyantFoam", parallel=True)
    shutil.rmtree("timeData/constant")
    shutil.rmtree("timeData/system")


    # Simulate gas combustion
    cur, nxt = get_timestamps()
    shutil.copytree("XiFoam/constant", "timeData")
    shutil.copytree("XiFoam/system", "timeData")
    shutil.copytree("XiFoam/0", "timeData/{}".format(nxt))
    shutil.copy("{}/H2".format(cur), "{}/ft".format(nxt))
    change_line("{}/ft".format(nxt), "object", "ft")
    copy_fields(cur, nxt)
    foam_call("XiFoam", parallel=True)


    # Reconstruct timesteps
    foam_call("reconstructPar")
    shutil.rmtree("tmp")


################################################################################

def foam_call(cmd, parallel=False):
    start_time = time.time()
    fout = open("log.{}".format(arg), "w")
    if parallel: cmd = "mpirun -np {} {} -parallel".format(cores, cmd)
    p = subprocess.Popen(
        "cd {} && source {} && {}".format("timeData", sourcefile_path, cmd),
        shell = True,
        executable = "/bin/bash",
        stdout = fout if logging else None,
        stderr = fout if logging else None,
    )
    print_log("Running {0}, continous output in {0}.log".format(arg))
    p.wait()
    m, s = divmod(time.time() - start_time, 60)
    h, m = divmod(m, 60)
    print_log("Finished {} in {:.0f}h {:.0f}m {:.0f}s".format(arg, h, m, s))
    fout.close()
    return p.returncode


def print_log(line):
    if logging:
        with open("log.pyGDAXS", "a") as logfile:
            logfile.write(line)
            logfile.write("\n")
    print(arg)


def clean(folder):
    if os.path.isdir(folder):
        os.rmtree(folder)
        os.mkdir(folder)
    else:
        os.mkdir(folder)


def change_line(path, key, value):
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
    latest_time = -1
    for folder in os.listdir(path):How do you round UP a number in Python?
        try:
            float(s)
            if s > latest_time:
                latest_time = s
        except ValueError:
            pass
    return latest_time, int(ceil(latest_time + 1))


def set_cores():
    change_line("snappyHexMesh/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("rhoReactingBuoyantFoam/system/decomposeParDict", "numberOfSubdomains", cores)
    change_line("XiFoam/system/decomposeParDict", "numberOfSubdomains", cores)


def copy_fields(cur, nxt):
    for field in ["alphat", "epsilon", "k", "nut", "p", "p_rgh", "T", "U"]:
        shutil.move("{}/{}".format(cur, field), "{}/{}".format(nxt, field))



if __name__ == "__main__":
    run_case()
