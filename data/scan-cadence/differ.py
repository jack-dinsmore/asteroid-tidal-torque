# Goal: spawn a bunch of runs that cover the parameter space.
from matplotlib import pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

plt.style.use("jcap")

param_names = ["\\gamma_0", "K_{22}", "K_{20}", "\Re K_{33}", "\Im K_{33}", "\Re K_{32}", "\Im K_{32}", "\Re K_{31}", "\Im K_{31}", "K_{30}"]

percentiles = {}
name_index = {}
true_sigma = []
cadences = []
THETA_TRUE = []

AXIS_SIZE = 12
LEGEND_SIZE = 12

N_DIM = None
N_PERCENTILES = None

def plot_best_fit(ax, xs, ys, scale):
    slope = np.cov(ys, xs)[0][1] / np.var(xs    )
    yint = np.mean(ys) - slope * np.mean(xs)
    ax.plot(xs, (xs * slope + yint) * scale, color='k', linewidth=1, linestyle='dotted')
    return slope

# Get percentiles
with open("percentiles.dat", 'r') as f:
    for line in f.readlines():
        if line == '': continue
        elements = line.split(':')
        name = elements[0]
        perc_array = []
        for percs in elements[1:]:
            perc_array.append([float(x) for x in percs.split(',')])
        perc_array = np.array(perc_array)
        N_DIM = perc_array.shape[0]
        N_PERCENTILES = perc_array.shape[1]
        percentiles[name] = perc_array

# Get true sigmas
for name in percentiles.keys():
    dir_name = name[:6]
    with open(f"{dir_name}/{dir_name}.txt", 'r') as f:
        max_j, max_l = f.readline().split(", ")
        max_j, max_l = (int(max_j), int(max_l))
        cadence = int(float(f.readline()))
        perigee = int(f.readline())
        radius = float(f.readline())
        speed = float(f.readline())
        spin = [float(x) for x in f.readline().split(',')]
        jlms = [float(x) for x in f.readline().split(',')]
        theta_true = [float(x) for x in f.readline().split(',')]
        theta_high = [float(x) for x in f.readline().split(',')]
        theta_low = [float(x) for x in f.readline().split(',')]
        sigma = [float(d) for d in f.readline().split(',')]
    THETA_TRUE = theta_true
    name_index[name] = int(dir_name[-2:])
    true_sigma = sigma[0]
    cadences.append(cadence / 60)

fig, axs = plt.subplots(figsize=(14, 8), ncols=3, nrows=4, sharex=True)
axs = axs.reshape(-1)
i = 0

for plot_index in range(N_DIM + 1):
    if plot_index == 9:
        continue
    param_data = np.zeros(len(cadences) * N_PERCENTILES).reshape(N_PERCENTILES, len(cadences))
    for f in percentiles.keys():
        param_data[:,name_index[f]] = percentiles[f][i]
    scale = 1e4 if i < 3 else 1
    axs[plot_index].plot(cadences, (param_data[1] - THETA_TRUE[i]) * scale / true_sigma, color=f"C{i}", linewidth=1)
    axs[plot_index].plot(cadences, (param_data[-1] - THETA_TRUE[i]) * scale / true_sigma, color=f"C{i}", linewidth=1)
    axs[plot_index].fill_between(cadences, (param_data[1]-THETA_TRUE[i]) * scale / true_sigma, 
        (param_data[-1]-THETA_TRUE[i]) * scale / true_sigma,  color=f"C{i}", alpha=0.3)

    axs[plot_index].plot(cadences, (param_data[2]-THETA_TRUE[i]) * scale / true_sigma, color=f"C{i}", linewidth=1)
    axs[plot_index].plot(cadences, (param_data[-2]-THETA_TRUE[i]) * scale / true_sigma, color=f"C{i}", linewidth=1)
    axs[plot_index].fill_between(cadences, (param_data[2]-THETA_TRUE[i]) * scale / true_sigma,
        (param_data[-2]-THETA_TRUE[i]) * scale / true_sigma, color=f"C{i}", alpha=0.3)

    axs[plot_index].plot(cadences, (param_data[3]-THETA_TRUE[i]) * scale / true_sigma, color=f"C{i}", linewidth=1, linestyle='dashed')
    axs[plot_index].axhline(y=0, color="k", linewidth=1)

    #axs[i].set_xscale('log')
    #axs[i].set_yscale('log')
    if i >= 3:
        axs[plot_index].set_ylabel(f"$|\Delta {param_names[i]}| / \sigma_\\theta$", size=AXIS_SIZE)
    else:
        axs[plot_index].set_ylabel(f"$|\Delta {param_names[i]}| / \sigma_\\theta\ (\\times 10^{{-4}})$", size=AXIS_SIZE)

    if plot_index in [6, 8, 10]:
        axs[plot_index].set_xlabel(f"$\Delta t$ (min)")

    EXTENT_AMOUNT = 100
    low = (param_data[-2]-param_data[0])*EXTENT_AMOUNT + param_data[0] - THETA_TRUE[i]
    high = (param_data[2]-param_data[0])*EXTENT_AMOUNT + param_data[0] - THETA_TRUE[i]
    mid = param_data[0] - THETA_TRUE[i]
    trues = ((low < 0) & (0 < mid)) | (mid < 0) & (0 < low) | ((high < 0) & (0 < mid)) | (mid < 0) & (0 < high)
    i += 1

axs[9].remove()
axs[11].remove()

custom_lines = [Line2D([0], [0], color='k', lw=4, alpha=0.3),
                Line2D([0], [0], color='k', lw=4, alpha=0.6),
                Line2D([0], [0], color='k', lw=1, linestyle='dashed')]
fig.legend(custom_lines, ['95\%', '68\%', '50\%'], ncol=3, framealpha=1, loc="lower right", prop={'size': LEGEND_SIZE})
fig.tight_layout()


line = plt.Line2D([0,1],[0.77, 0.77], transform=fig.transFigure, color="black")
fig.add_artist(line)

plt.savefig("differ.pdf")
plt.savefig("differ.png")
plt.show()