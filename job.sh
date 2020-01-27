#!/bin/bash

#SBATCH --job-name=lgpu0009_test
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=3
#SBATCH --ntasks-per-node=1
#SBATCH --time=0:01:00
#SBATCH --mem=50000M
#SBATCH --partition=gpu_shared_course
#SBATCH --gres=gpu:1
#SBATCH --output=slurm_out/slurm_test_grad_rand.out

module purge
module load 2019
module load CUDA/10.0.130
module Miniconda2

source activate dl
srun python3 pixel_perturbation.py --grads fullgrad gradcam random --batch_size 10 --n_images 5000 --n_random_runs 5 --most_salient False --model vgg --model_type 16_bn --target_layer features

source deactivate dl
