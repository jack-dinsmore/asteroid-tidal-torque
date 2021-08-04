#!/bin/bash

# Slurm sbatsh options
#SBATCH -o 
#SBATCH --exclusive
#ggSBATCH --gres=gpu:volta:1

source /etc/profile

module load anaconda/2021a

python fit.py
