import numpy as np
import pandas as pd
import torch
import torchvision

import random
import argparse

from modeling import trainer, model
from data_loading import dataloaders, transforms

from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm
import multiprocessing


torch.manual_seed(0)
argp = argparse.ArgumentParser()
argp.add_argument(
    "--function", help="Choose train or evaluate"
)  # TODO: add behavior for pretrain and eval
argp.add_argument(
    "--writing_params_path",
    type=str,
    help="Path to the writing params file",
    default="BEST_FUSION.params",
)
argp.add_argument(
    "--reading_params_path",
    type=str,
    help="Path to the reading params file",
    default="./model/best_model.params",
)
argp.add_argument(
    "--outputs_path",
    type=str,
    help="Path to the output predictions",
    default="new.csv",
    required=False,
)
argp.add_argument(
    "--loss_path",
    type=str,
    help="Path to the output losses",
    default="base.txt",
    required=False,
)
argp.add_argument(
    "--max_epochs",
    type=int,
    help="Number of epochs to train for",
    default=25,
    required=False,
)
argp.add_argument(
    "--learning_rate", type=float, help="Learning rate", default=2e-4, required=False
)
argp.add_argument(
    "--seed", type=int, help="Number of epochs to train for", default=0, required=False
)
argp.add_argument(
    "--model_name",
    type=str,
    help="Name of model to use",
    default="FUSION",
    required=False,
)
args = argp.parse_args()

if __name__ == "__main__":
    # Save the device
    device = torch.cuda.current_device() if torch.cuda.is_available() else "cpu"
    print(device)
    # video_transformer = transforms.VideoFilePathToTensor(
    #     max_len=22 * 3, fps=3, padding_mode="zero"
    # )
    video_transformer = transforms.VideoFilePathToTensor(
        max_len=None, fps=10, padding_mode="last"
    )
    H, W = 256, 256
    transforms = torchvision.transforms.Compose(
        [
            transforms.VideoResize([H, W]),
            # transforms.VideoRandomHorizontalFlip(),
            # transforms.NormalizeVideoFrames(),
        ]
    )

    labels = ['y_fall_risk']

    if args.function == "pretrain":
        pass

    elif args.function == "train":
        # get the dataloaders. can make test and val sizes 0 if you don't want them
        train_dl, val_dl, test_dl = dataloaders.get_fusion_data_loaders(
            video_transformer=video_transformer,
            batch_size=1,
            val_batch_size=1,
            test_batch_size=1,
            transforms=transforms,
            preload_videos=False,
            num_workers=0,
        )
        # TensorBoard training log
        writer = SummaryWriter(log_dir="expt/")

        train_config = trainer.TrainerConfig(
            max_epochs=args.max_epochs,
            learning_rate=args.learning_rate,
            num_workers=4,
            writer=writer,
            ckpt_path="expt/params.pt",
        )

        model = model.FusionModel(num_features=123, num_outputs=3, num_mc_outputs=5, mc_model_type="openposeMC", mc_model_path=args.reading_params_path, device=device)

        trainer = trainer.Trainer(
            model=model,
            train_dataloader=train_dl,
            test_dataloader=test_dl,
            config=train_config,
            val_dataloader=val_dl,
            median_freq_weights=True,
        )
        train_losses = []
        val_losses = []
        best_val_loss = np.inf
        for epoch in range(args.max_epochs):
            print("Epoch: ", epoch)
            train_losses.append(trainer.train(split="train", step=epoch))
            val_loss = trainer.train(split="val", step=epoch)
            val_losses.append(val_loss)
            print("Val loss:", val_loss)
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                print("Saving model after epoch", epoch)
                torch.save(model.state_dict(), args.writing_params_path)
            torch.save(model.state_dict(), f"{args.model_name}_{epoch}.params")
        # write csv of losses
        with open(args.loss_path, "w") as f:
            for train_loss, val_loss in zip(train_losses, val_losses):
                f.write(f"{train_loss},{val_loss}\n")
