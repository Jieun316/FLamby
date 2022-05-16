import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from flamby.utils import check_dataset_from_config


class HeartDiseaseRaw(Dataset):
    """Pytorch dataset containing all the features, labels and
    metadata for the Heart Disease dataset.
    Attributes
    ----------
    data_dir : str, Where data files are located
    data_paths: list[str], The list with the path towards all features.
    features_labels: list[int], The list with all classification labels for all features
    features_centers: list[int], The list for all centers for all features
    features_sets: list[str], The list for all sets (train/test) for all features
    X_dtype: torch.dtype, The dtype of the X features output
    y_dtype: torch.dtype, The dtype of the y label output
    debug: bool, Whether or not we use the dataset with only part of the features
    """

    def __init__(self, X_dtype=torch.float32, y_dtype=torch.float32, debug=False):
        """See description above
        Parameters
        ----------
        X_dtype : torch.dtype, optional
            Dtype for inputs `X`. Defaults to `torch.float32`.
        y_dtype : torch.dtype, optional
            Dtype for labels `y`. Defaults to `torch.int64`.
        debug : bool, optional,
            Whether or not to use only the part of the dataset downloaded in
            debug mode. Defaults to False.
        """
        dict = check_dataset_from_config("fed_heart_disease", debug)
        self.data_dir = Path(dict["dataset_path"])

        self.X_dtype = X_dtype
        self.y_dtype = y_dtype
        self.debug = debug

        self.centers_number = {"cleveland": 0, "hungarian": 1, "switzerland": 2, "va": 3}

        self.features = pd.DataFrame()
        self.labels = pd.DataFrame()
        self.centers = []
        self.sets = []

        self.train_fraction = 0.66

        # to ensure the split is static
        np.random.seed(8)

        for center_data_file in self.data_dir.glob("*.data"):

            center_name = os.path.basename(center_data_file).split(".")[1]

            df = pd.read_csv(center_data_file, header=None)
            df = df.replace("?", np.NaN).drop([10, 11, 12], axis=1).dropna(axis=0)

            center_X = df.iloc[:, :-1]
            center_y = df.iloc[:, -1]

            self.features = pd.concat((self.features, center_X), ignore_index=True)
            self.labels = pd.concat((self.labels, center_y), ignore_index=True)

            self.centers += [self.centers_number[center_name]] * center_X.shape[0]

            # proposed modification to introduce shuffling before splitting the center
            # into train / test sets (with0ut this there is a problem for center 1)

            # nb_train = int(center_X.shape[0] * self.train_fraction)
            # nb_test = center_X.shape[0] - nb_train
            # self.sets += ["train"] * nb_train
            # self.sets += ["test"] * nb_test
            nb = int(center_X.shape[0])
            for _ in range(nb):
                if np.random.rand() < self.train_fraction:
                    self.sets += ["train"]
                else:
                    self.sets += ["test"]

        # encode dummy variables for categorical variables
        self.features = pd.get_dummies(self.features, columns=[2, 6], drop_first=True)
        self.features = [
            torch.from_numpy(self.features.loc[i].values.astype(np.float32)).to(
                self.X_dtype
            )
            for i in range(len(self.features))
        ]

        # keep 0 (no disease) and put 1 for all other values (disease)
        self.labels.where(self.labels == 0, 1, inplace=True)
        self.labels = torch.from_numpy(self.labels.values).to(self.X_dtype)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        assert idx < len(self.features), "Index out of range."

        X = self.features[idx]
        y = self.labels[idx]

        return X, y


class FedHeartDisease(HeartDiseaseRaw):
    """
    Pytorch dataset containing for each center the features and associated labels
    for Heart Disease federated classification.
    One can instantiate this dataset with train or test data coming from either
    of the 4 centers it was created from or all data pooled.
    The train/test split are arbitrarily fixed.
    """

    def __init__(
        self,
        center=0,
        train=True,
        pooled=False,
        X_dtype=torch.float32,
        y_dtype=torch.float32,
        debug=False,
    ):
        """Instantiate the dataset
        Parameters
        pooled : bool, optional
            Whether to take all data from the 2 centers into one dataset, by
            default False
        X_dtype : torch.dtype, optional
            Dtype for inputs `X`. Defaults to `torch.float32`.
        y_dtype : torch.dtype, optional
            Dtype for labels `y`. Defaults to `torch.int64`.
        debug : bool, optional,
            Whether or not to use only the part of the dataset downloaded in
            debug mode. Defaults to False.
        """

        super().__init__(X_dtype=X_dtype, y_dtype=y_dtype, debug=debug)
        assert center in [0, 1, 2, 3]

        self.chosen_centers = [center]
        if pooled:
            self.chosen_centers = [0, 1, 2, 3]

        if train:
            self.chosen_sets = ["train"]
        else:
            self.chosen_sets = ["test"]

        to_select = [
            (self.sets[idx] in self.chosen_sets)
            and (self.centers[idx] in self.chosen_centers)
            for idx, _ in enumerate(self.features)
        ]

        self.features = [fp for idx, fp in enumerate(self.features) if to_select[idx]]
        self.sets = [fp for idx, fp in enumerate(self.sets) if to_select[idx]]
        self.labels = [fp for idx, fp in enumerate(self.labels) if to_select[idx]]
        self.centers = [fp for idx, fp in enumerate(self.centers) if to_select[idx]]

