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
)
argp.add_argument(
    "--writing_params_path",
    type=str,
    help="Path to the writing params file",
    default="base.params",
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
    default=15,
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
    default="Survey",
    required=False,
)
args = argp.parse_args()

if __name__ == "__main__":
    # Save the device
    device = torch.cuda.current_device() if torch.cuda.is_available() else "cpu"
    print(device)
    video_transformer = transforms.VideoFilePathToTensor(
        max_len=22 * 3, fps=3, padding_mode="zero"
    )
    H, W = 256, 256
    transforms = torchvision.transforms.Compose(
        [
            transforms.VideoResize([H, W]),
            # transforms.VideoRandomHorizontalFlip(),
            transforms.NormalizeVideoFrames(),
        ]
    )

    labels = ['y_fall_risk']

    if args.function == "pretrain":
        pass

    elif args.function == "train":
        # get the dataloaders. can make test and val sizes 0 if you don't want them
        train_dl, val_dl, test_dl = dataloaders.get_survey_data_loaders(
            batch_size=16,
            val_batch_size=16,
            test_batch_size=1,
            transforms=transforms,
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

        model = model.SurveyModel(num_features=124, num_outputs=3, device=device)

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
    elif args.function == "evaluate":
        train_dl, val_dl, test_dl = dataloaders.get_survey_data_loaders(
            batch_size=1,
            val_batch_size=1,
            test_batch_size=1,
            transforms=transforms,
        )
        model = model.SurveyModel(num_features=124, num_outputs=3, device=device)

        model.load_state_dict(
            torch.load(args.reading_params_path, map_location=torch.device("cpu"))
        )
        
        model = model.to(device)
        model.eval()
        torch.set_grad_enabled(False)
        predictions = []

        pbar = tqdm(enumerate(test_dl), total=len(test_dl))
        # pred_cols = [f'pred_{c}' for c in dataset.targets_sentence.columns] + [f'pred_word_{c}' for c in dataset.targets_words.columns] + [f'pred_{c}' for c in dataset.targets_phones.columns]
        pred_cols = ["prob_0", "prob_1", "prob_2"]
        actual_cols = labels
        for it, (subj_id, x, y) in pbar:
            print(it)
            # place data on the correct device
            with torch.no_grad():
                x = x.to(device)
                pred = model(x)[0]
                print(pred)
                print(y)
                predictions.append(
                    (
                        {
                            "id": subj_id[0],
                            **dict(zip(pred_cols, pred.tolist()[0])),
                            **dict(zip(actual_cols, y.tolist()[0])),
                        }
                    )
                )

        pd.DataFrame(predictions).to_csv(args.outputs_path, index=False)