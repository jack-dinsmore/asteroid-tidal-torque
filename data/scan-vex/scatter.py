# Goal: spawn a bunch of runs that cover the parameter space.
from matplotlib import pyplot as plt
import numpy as np

LOW_ORDER_INDEX = 1
BASE_NAME = f"vex"
LOW_V_EX= 1000
HIGH_V_EX = 10000
NUM_DIVISIONS = 48 # Run with 8 cores per process.
LOW_ORDER = [(0.39269908169, 0, -0.09766608), (0.39269908169, 0.05200629, -0.2021978)][LOW_ORDER_INDEX]
HIGH_ORDER = [0, 0, 0, 0, 0, 0, 0]

# Fix product, vary ratio

def get_text(perigee):
    return """0, 2
120
5
1000
{}
0.00006464182, 0.00012928364, -0.00012928364
1.0
{}, {}, {}, {}, {}, {}, {}, {}, {}, {}
0.78539816339, 0.125, 0, 1, 1, 1, 1, 1, 1, 1
-0.78539816339, -0.125, -0.25, -1, -1, -1, -1, -1, -1, -1
1e-2, 1e-5""".format(perigee, LOW_ORDER[0], LOW_ORDER[1], LOW_ORDER[2], HIGH_ORDER[0], HIGH_ORDER[1],
    HIGH_ORDER[2], HIGH_ORDER[3], HIGH_ORDER[4], HIGH_ORDER[5], HIGH_ORDER[6])

for ratio_index, perigee in enumerate(np.linspace(LOW_V_EX, HIGH_V_EX, NUM_DIVISIONS)):
    f = open("../../staged/{}-{:02}.txt".format(BASE_NAME, ratio_index), 'w')
    f.write(get_text(perigee))
    f.close()
