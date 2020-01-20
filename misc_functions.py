#
# Copyright (c) 2019 Idiap Research Institute, http://www.idiap.ch/
# Written by Suraj Srinivas <suraj.srinivas@idiap.ch>
#

""" Misc helper functions """

import os
import cv2
import numpy as np
import subprocess

import torch
import torchvision.transforms as transforms

from saliency.fullgrad import FullGrad
from saliency.simple_fullgrad import SimpleFullGrad


class NormalizeInverse(transforms.Normalize):
    # Undo normalization on images

    def __init__(self, mean, std):
        mean = torch.as_tensor(mean)
        std = torch.as_tensor(std)
        std_inv = 1 / (std + 1e-7)
        mean_inv = -mean * std_inv
        super(NormalizeInverse, self).__init__(mean=mean_inv, std=std_inv)

    def __call__(self, tensor):
        return super(NormalizeInverse, self).__call__(tensor.clone())


def create_folder(folder_name):
    try:
        subprocess.call(['mkdir','-p',folder_name])
    except OSError:
        None

def save_saliency_map(image, saliency_map, filename):
    """ 
    Save saliency map on image.
    
    Args:
        image: Tensor of size (3,H,W)
        saliency_map: Tensor of size (1,H,W) 
        filename: string with complete path and file extension

    """

    image = image.data.cpu().numpy()
    saliency_map = saliency_map.data.cpu().numpy()

    saliency_map = saliency_map - saliency_map.min()
    saliency_map = saliency_map / saliency_map.max()
    saliency_map = saliency_map.clip(0,1)

    saliency_map = np.uint8(saliency_map * 255).transpose(1, 2, 0)
    saliency_map = cv2.resize(saliency_map, (224,224))

    image = np.uint8(image * 255).transpose(1,2,0)
    image = cv2.resize(image, (224, 224))

    # Apply JET colormap
    color_heatmap = cv2.applyColorMap(saliency_map, cv2.COLORMAP_JET)
    
    # Combine image with heatmap
    img_with_heatmap = np.float32(color_heatmap) + np.float32(image)
    img_with_heatmap = img_with_heatmap / np.max(img_with_heatmap)

    cv2.imwrite(filename, np.uint8(255 * img_with_heatmap))


def compute_and_store_saliency_maps(sample_loader, model, device, directory):
    # Initialize FullGrad objects
    fullgrad = FullGrad(model)
    simple_fullgrad = SimpleFullGrad(model)

    simple_grad_path = os.path.join(directory, "simple")
    full_grad_path = os.path.join(directory, "full")
    
    create_folder(simple_grad_path)
    create_folder(full_grad_path)

    for batch_idx, (data, target) in enumerate(sample_loader):
        data, target = data.to(device).requires_grad_(), target.to(device)

        _ = model.forward(data)

        cam = fullgrad.saliency(data)
        cam_simple = simple_fullgrad.saliency(data)

        filename = "saliency_map_" + str(batch_idx)

        torch.save(cam, os.path.join(simple_grad_path, filename))
        torch.save(cam_simple, os.path.join(full_grad_path, filename))


def remove_salient_pixels(image_batch, saliency_maps, num_pixels=100, most_salient=True, replacement=1.0):
    # Check that the data and the saliency map have the same batch size and the
    # same image dimention.
    assert image_batch.size()[0] == saliency_maps.size()[0], \
            "Images and saliency maps do not have the same batch size."
    assert image_batch.size()[2:3] == saliency_maps.size()[2:3], \
            "Images and saliency maps do not have the same image size."

    [column_size, row_size] = image_batch.size()[2:4]
    indexes = torch.topk(saliency_maps.view((-1)), k=num_pixels, largest=most_salient)[1]
    rows = indexes / row_size
    columns = indexes % row_size
    image_batch[:, :, rows, columns] = replacement
    return image_batch

