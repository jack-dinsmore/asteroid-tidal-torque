# Goal: spawn a bunch of runs that cover the parameter space.
from matplotlib import pyplot as plt
import numpy as np

LOW_ORDER_INDEX = 1
BASE_NAME = f"ratio-prod-{LOW_ORDER_INDEX}"
LOW_LOG_RATIO = 0
HIGH_LOG_RATIO = -5
NUM_RATIO_DIVISIONS = 48 # Run with 12 cores per process.
LOW_ORDER = [(0.39269908169, 0, -0.09766608), (0.39269908169, 0.05200629, -0.2021978)][LOW_ORDER_INDEX]
HIGH_ORDER = [0, 0, 0, 0, 0, 0, 0]
PRODUCT = 10**-7

# Fix product, vary ratio

def get_text(sigma_theta, ratio):
    return """0, 3
120
5
1000
6000
0.00006464182, 0.00012928364, -0.00012928364
1.0
{}, {}, {}, {}, {}, {}, {}, {}, {}, {}
0.78539816339, 0.125, 0, 1, 1, 1, 1, 1, 1, 1
-0.78539816339, -0.125, -0.25, -1, -1, -1, -1, -1, -1, -1
{}, {}""".format(LOW_ORDER[0], LOW_ORDER[1], LOW_ORDER[2], HIGH_ORDER[0], HIGH_ORDER[1],
    HIGH_ORDER[2], HIGH_ORDER[3], HIGH_ORDER[4], HIGH_ORDER[5], HIGH_ORDER[6], sigma_theta, ratio)

for ratio_index, log_ratio in enumerate(np.linspace(LOW_LOG_RATIO, HIGH_LOG_RATIO, NUM_RATIO_DIVISIONS)):
    f = open("../../staged/{}-{:02}.txt".format(BASE_NAME, ratio_index), 'w')
    f.write(get_text(np.sqrt(PRODUCT / 10**log_ratio), 10**log_ratio))
    f.close()
