import torch
import torch.nn as nn
import torch.nn.functional as F
from math import isclose


class FullGrad():
    """
    Compute FullGrad saliency map and full gradient decomposition
    """

    def __init__(self, model, im_size=(3, 224, 224)):
        self.model = model
        self.im_size = (1,) + im_size
        self.model.eval()
        self.device = next(model.parameters()).device


    def fullGradientDecompose(self, image, target_class=None):
        """
        Compute full-gradient decomposition for an image
        """

        image = image.requires_grad_()
        out, features = model.getFeatures(image)
        output = model.forward(image)

        if target_class is None:
            target_class = output.data.max(1, keepdim=True)[1]

        agg = 0
        for i in range(image.size(0)):
            agg += out[i, target_class[i]]

        model.zero_grad()
        # Gradients w.r.t. input and features
        model.backward()
        gradients = torch.autograd.grad(outputs=agg, inputs=features, only_inputs=True)

        # First element in the feature list is the image
        input_gradient = gradients[0]

        # Loop through remaining gradients
        bias_gradient = []
        for i in range(1, len(gradients)):
            bias_gradient.append(gradients[i] * self.blockwise_biases[i])

        return input_gradient, bias_gradient

    def _postProcess(self, input):
        # Absolute value
        input = abs(input)

        # Rescale operations to ensure gradients lie between 0 and 1
        input = input - input.min()
        input = input / (input.max())
        return input

    def saliency(self, image, target_class=None):

        # FullGrad saliency

        self.model.eval()
        input_grad, bias_grad = self.fullGradientDecompose(image, target_class=target_class)

        # Input-gradient * image
        grd = input_grad[0] * image
        gradient = self._postProcess(grd).sum(1, keepdim=True)
        cam = gradient

        im_size = image.size()

        # Bias-gradients of conv layers
        for i in range(len(bias_grad)):
            # Checking if bias-gradients are 4d / 3d tensors
            if len(bias_grad[i].size()) == len(im_size):
                temp = self._postProcess(bias_grad[i])
                if len(im_size) == 3:
                    gradient = F.interpolate(temp, size=im_size[2], mode='bilinear', align_corners=False)
                elif len(im_size) == 4:
                    gradient = F.interpolate(temp, size=(im_size[2], im_size[3]), mode='bilinear', align_corners=False)
                cam += gradient.sum(1, keepdim=True)

        return cam

