
import os

import torch
from torchvision import datasets, transforms
from datetime import datetime

# Import saliency methods and models
import argparse
from saliency.fullgrad import FullGrad
from saliency.simple_fullgrad import SimpleFullGrad
from saliency.inputgradient import Inputgrad
from models.vgg import vgg16_bn, vgg11
from models.resnet import resnet18
from misc_functions import create_folder, compute_and_store_saliency_maps, remove_salient_pixels, remove_random_salient_pixels
import copy
import matplotlib.pyplot as plt
from torch.optim import lr_scheduler


# PATH variables
PATH = os.path.dirname(os.path.abspath(__file__)) + '/'
data_PATH= PATH + 'dataset/'

torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False


def train(data_loader, model, k_most_salient=0, saliency_path="", \
        saliency_method_name=""):
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.classifier.parameters(), lr=ARGS.initial_learning_rate, momentum=0.9)
    scheduler = lr_scheduler.StepLR(optimizer, step_size=ARGS.lr_decresing_step, gamma=ARGS.lr_gamma)
    model.train()

    losses = []
    loss_steps = []
    num_batches = 0.0
    for epoch in range(ARGS.epochs):
        accuracy = 0.0
        for step, (batch_inputs, batch_targets) in enumerate(data_loader):
            num_batches += 1
            batch_inputs, batch_targets = batch_inputs.to(ARGS.device), \
                                          batch_targets.to(ARGS.device)
            if k_most_salient != 0:
                saliency_map = torch.load(os.path.join(saliency_path, \
                        "saliency_map_" + str(step)))
                data = remove_salient_pixels(batch_inputs, saliency_map, \
                        num_pixels=k_most_salient, most_salient=ARGS.most_salient)
            else:
                data = batch_inputs
            optimizer.zero_grad()
            output = model.forward(data)
            
            loss = criterion(output, batch_targets)
            accuracy += sum(batch_targets == torch.argmax(output, 1))

            loss.backward()
            optimizer.step()

            if step % ARGS.print_step == 0 and step != 0:
                losses += [loss]
                loss_steps += [num_batches]
                accuracy = float(accuracy) / float(ARGS.batch_size * ARGS.print_step)

                if (len(losses) > 2 and abs(losses[-1] - losses[-2]) < 0.0001):
                    break
                print("[{}] Train Step {:04d}/{:04d}, Batch Size = {}, "
                      "Accuracy = {:.2f}, Train Loss = {:.3f}".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M"), step,
                        len(data_loader.dataset), ARGS.batch_size, accuracy, loss
                ))
                accuracy = 0.0

            if ARGS.max_train_steps == step:
                break
        
        scheduler.step()

    # plot
    plt.figure(1)
    plt.clf()
    plt.plot(loss_steps, losses)
    plt.ylabel('Loss')
    plt.xlabel('Batches')
    if k_most_salient != 0:
        figname = saliency_method_name + "_" + str(k_most_salient) + ".jpeg"
    else:
        figname = "initial_model.jpeg"
    plt.savefig(os.path.join("results", "remove_and_retrain", figname))


def test(data_loader, model, max_steps, k_most_salient=0, saliency_path=""):
    model.eval()
    accuracy = 0.0
    num_batches = 0
    for step, (batch_inputs, batch_targets) in enumerate(data_loader):
        batch_inputs, batch_targets = batch_inputs.to(ARGS.device), \
                                      batch_targets.to(ARGS.device)
        if k_most_salient != 0: 
            saliency_map = torch.load(os.path.join(saliency_path, \
                    "saliency_map_" + str(step)))
            data = remove_salient_pixels(batch_inputs, saliency_map, \
                    num_pixels=k_most_salient, most_salient=ARGS.most_salient)
        else:
            data = batch_inputs
        batch_inputs.requires_grad = False
        
        output = model.forward(batch_inputs)
        accuracy += sum(batch_targets == torch.argmax(output, 1))
        num_batches += 1
        if ARGS.max_train_steps == step:
            break
    print(accuracy)
    return float(accuracy) / float(num_batches * ARGS.batch_size)


def init_model():
    model = vgg11(pretrained=True, in_size=32).to(ARGS.device)
    for param in  model.features:
        param.requires_grad = False

    model.classifier[0] = torch.nn.Linear(in_features=512, out_features=256, bias=True).to(ARGS.device)
    model.classifier[3] = torch.nn.Linear(in_features=256, out_features=128, bias=True).to(ARGS.device)
    model.classifier[6] = torch.nn.Linear(in_features=128, out_features=10, bias=True).to(ARGS.device)

    return model


def get_saliency_methods(grad_names, initial_model):
    saliency_methods = []
    for grad_name in grad_names:
        if grad_name == "fullgrad":
            saliency_methods += [(FullGrad(initial_model, im_size=(3, 32, 32)), "FullGrad")]
        elif grad_name == "simplegrad":
            saliency_methods += [(SimpleFullGrad(initial_model), "SimpleFullGrad")]
        elif grad_name == "inputgrad":
            saliency_methods += [(Inputgrad(initial_model), "InputGrad")]
        elif grad_name == "random":
            saliency_methods += [(None, "RandomGrad")]
    return saliency_methods


def remove_and_retrain(train_set_loader, test_set_loader):
    initial_model = init_model()
    train(train_set_loader, initial_model)
    initial_accuracy = test(test_set_loader, initial_model, ARGS.max_train_steps)
    
    saliency_methods = get_saliency_methods(ARGS.grads, initial_model)

    total_features = ARGS.img_size * ARGS.img_size
    accuracies = torch.zeros((len(saliency_methods), len(ARGS.k)))
    for method_idx, (saliency_method, method_name) in enumerate(saliency_methods):
        train_saliency_path = os.path.join(data_PATH, "saliency_maps", method_name + "_vgg11", "train")
        compute_and_store_saliency_maps(train_set_loader, initial_model, \
            ARGS.device, ARGS.max_train_steps, saliency_method, train_saliency_path)

        test_saliency_path = os.path.join(data_PATH, "saliency_maps", method_name + "_vgg11", "test")
        compute_and_store_saliency_maps(test_set_loader, initial_model, \
            ARGS.device, ARGS.max_train_steps, saliency_method, test_saliency_path)

        for k_idx, k in enumerate(ARGS.k):
            print("Run saliency method: ", method_name)

            model = init_model()
            train(train_set_loader, k_most_salient=int(k * total_features), \
                  saliency_path=train_saliency_path, \
                  saliency_method_name=method_name)
            accuracy = test(test_set_loader, model, \
                            ARGS.max_train_steps, \
                            k_most_salient=int(k * total_features), \
                            saliency_path=test_saliency_path)
            accuracies[method_idx, k_idx] = accuracy
        plt.figure(0)
        plt.plot([k * 100 for k in ARGS.k], list(accuracies[method_idx]), label=method_name + str(k))
    plt.figure(0)
    plt.ylabel('Accuracy')
    plt.xlabel('k %')
    plt.legend()
    plt.savefig(os.path.join("results", "remove_and_retrain", "final_result.jpeg"))


def compute_modified_datasets(train_set_loader, test_set_loader):
    '''
    initial_model = init_model()
    train(train_set_loader, initial_model)
    initial_accuracy = test(test_set_loader, initial_model, ARGS.max_train_steps)
    print(initial_accuracy)
    torch.save(initial_model, os.path.join("models", "trained_vgg11_cifar10"))
    '''
    initial_model = torch.load(os.path.join("models", "trained_vgg11_cifar10")) 

    saliency_methods = get_saliency_methods(ARGS.grads, initial_model)

    total_features = ARGS.img_size * ARGS.img_size
    accuracies = torch.zeros((len(saliency_methods), len(ARGS.k)))
    for method_idx, (saliency_method, method_name) in enumerate(saliency_methods):
        for dataset, dataloader in [("train", train_set_loader), ("test", test_set_loader)]:
            saliency_path = os.path.join(data_PATH, "saliency_maps", method_name + "_vgg11", dataset)
            if saliency_method != None:
                compute_and_store_saliency_maps(dataloader, initial_model, \
                    ARGS.device, ARGS.max_train_steps, saliency_method, saliency_path)
            for k_idx, k in enumerate(ARGS.k):
                batches = []
                num_pixels = int(k * total_features)

                dataset_path = os.path.join(data_PATH, "modified_cifar_10", method_name, str(num_pixels))
                create_folder(dataset_path)

                for step, (batch_inputs, batch_targets) in enumerate(dataloader):
                    if method_name == "RandomGrad":
                        data = remove_random_salient_pixels(batch_inputs, 42, k, im_size=32)
                    else:
                        saliency_map = torch.load(os.path.join(saliency_path, \
                            "saliency_map_" + str(step)))
                        data = remove_salient_pixels(batch_inputs, saliency_map, \
                            num_pixels=num_pixels, most_salient=ARGS.most_salient)
                    batches += [data]
                    if step == ARGS.max_train_steps:
                        break

                modified_dataset = torch.utils.data.ConcatDataset(batches)
                torch.save(modified_dataset, os.path.join(dataset_path, dataset))

def main():
    # same transformations for each dataset
    transform_standard = transforms.Compose([
        transforms.Resize((ARGS.img_size, ARGS.img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]), ])
    dataset = data_PATH + "/cifar/"
    train_set = datasets.CIFAR10(dataset, train=True, transform=transform_standard, \
        target_transform=None, download=True)
    test_set = datasets.CIFAR10(dataset, train=False, transform=transform_standard, \
        target_transform=None, download=True)
    train_set_loader = torch.utils.data.DataLoader(train_set, batch_size=ARGS.batch_size, shuffle=False)
    test_set_loader = torch.utils.data.DataLoader(test_set, batch_size=ARGS.batch_size, shuffle=False)

    #remove_and_retrain(train_set_loader, test_set_loader)
    compute_modified_datasets(train_set_loader, test_set_loader)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--k', default=[0.001, 0.005, 0.01, 0.05, 0.1], type=float,nargs="+",
                        help='Percentage of k% most salient pixels')
    parser.add_argument('--most_salient', default="True", type=str,
                        help='most salient = True or False depending on retrain or pixel perturbation')
    parser.add_argument('--grads', default=["fullgrad"], type=str, nargs='+',
                        help='which grad methods to be applied')
    parser.add_argument('--device', default="cuda:0", type=str,
                        help='cpu or gpu')
    parser.add_argument('--target_layer', default="layer4", type=str,
                        help='Which layer to be visualized in GRADCAM')
    parser.add_argument('--n_random_runs', default=5, type=int,
                        help='Number of runs for random pixels to be removed to decrease std of random run')
    parser.add_argument('--replacement', default="black", type=str,
                        help='black = 1.0 or mean = [0.485, 0.456, 0.406]')
    parser.add_argument('--batch_size', default=1, type=int,
                        help='Number of images passed through at once')
    parser.add_argument('--max_train_steps', default=-1, type=int,
                        help='Maximum number of training steps')
    parser.add_argument('--epochs', default=100, type=int,
                        help='Maximum number of epochs')
    parser.add_argument('--initial_learning_rate', default=0.001, type=float,
                        help='Initial learning rate')
    parser.add_argument('--lr_decresing_step', default=10, type=int,
                        help='Number of training steps between decreasing the learning rate')
    parser.add_argument('--lr_gamma', default=0.1, type=float,
                        help='mltiplier for changing the lr')
    parser.add_argument('--img_size', default=32, type=int,
                        help='Row and Column size of the image')
    parser.add_argument('--print_step', default=500, type=int,
                        help='Number of batches after which we print')


    ARGS = parser.parse_args()
    main()


