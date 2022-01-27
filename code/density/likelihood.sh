#!/bin/bash

# Slurm sbatsh options
#SBATCH -o likelihood.log
#SBATCH -c 12

source /etc/profile

module load anaconda/2021a

python likelihood.py
