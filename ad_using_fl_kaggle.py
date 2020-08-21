# -*- coding: utf-8 -*-
"""AD using FL Kaggle.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1aPM86kk8zyLrqdDjiYKEjbljWMN_ERkW
"""

from google.colab import drive
drive.mount('/content/drive')

import os
os.chdir('/content/drive/My Drive/FinalYearProject Coding Phase')
print(os.getcwd())

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

maindataset_path = "/content/drive/My Drive/FinalYearProject Coding Phase/iotdataset1.csv"
data = pd.read_csv(maindataset_path)
print(data.columns)

data.head()

data[data['normality']!='normal']

"""**Preprocessing (as per the base paper)**"""

data.loc[data.value=='twenty',"value"] = '20.0'
data.loc[data.value=='false',"value"] = '0'
data.loc[data.value=='true',"value"] = '1'
data.loc[data.value=='none',"value"] = '0'
data.loc[data.value=='0',"value"] = '0.0'
data['value'] = data['value'].fillna(value='60.0')
data = data.drop(data.index[data.value.str.contains("org.*")])
data.value = data.value.astype(float)

"""**Data Cleaning**"""

data['accessedNodeType'] = data['accessedNodeType'].fillna(value='/Malicious')
data.head()

data['normality'].unique()

"""**Visualization**"""

normality_count = data.normality.value_counts()
indices = ['normal', 'DoSattack', 'scan', 'malitiousControl', 'malitiousOperation', 'spying', 'dataProbing', 'wrongSetUp']
plt.figure(figsize=(10,5))
ax=plt.subplot(111)
plt.grid()
plt.bar(indices, normality_count.values)
plt.ylabel('Number of Occurrences', fontsize=20)
plt.xlabel('Normality', fontsize=20)
plt.xticks(rotation=90, fontsize=15)
plt.yticks(fontsize=15)
plt.show()

data = data.drop('timestamp',axis=1)

data.head()

#The Features
df = data.iloc[:,:-1]

from sklearn.preprocessing import LabelEncoder

#converting features in to integers
df = df.apply(LabelEncoder().fit_transform)

df.head()

df.dtypes

#scaling
final_df = df/df.max()
final_df.head()

X = final_df.values
# final dataframe has 11 features
print("Shape of feature matrix : ",X.shape)

"""**Using Label encoder to convert threat types into numerics**"""

threat_types = data["normality"].values
encoder = LabelEncoder()
y = encoder.fit_transform(threat_types)
print("Shape of target vector : ",y.shape)

np.unique(y)

"""**Test Train Split**"""

from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split( X, y, test_size=0.4, random_state=42, stratify=y)
print("Number of records in training data : ", X_train.shape)
print("Number of records in test data : ", X_test.shape)
print("Total distinct number of threat types in training data : ",len(set(y_train)))
print("Total distinct number of threat types in test data : ",len(set(y_test)))

#!pip install syft

import torch as th
import syft as sy

# Hook PyTorch ie add extra functionalities to support Federated Learning
hook = sy.TorchHook(th)
# Sets the seed for generating random numbers.
th.manual_seed(1)
# Select CPU computation, in case you want GPU use "cuda" instead
device = th.device("cpu")
# Data will be distributed among these VirtualWorkers.
# Remote training of the model will happen here: gateway1 and gateway2
gateway1 = sy.VirtualWorker(hook, id="gateway1")
gateway2 = sy.VirtualWorker(hook, id="gateway2")

# Number of times we want to iterate over whole training data
BATCH_SIZE = 1000
EPOCHS = 5
LOG_INTERVAL = 5
lr = 0.01

n_feature = X_train.shape[1]
n_class = np.unique(y_train).shape[0]

print("Number of training features : ",n_feature)
print("Number of training classes : ",n_class)

# Create pytorch tensor from X_train,y_train,X_test,y_test
train_inputs = th.tensor(X_train,dtype=th.float)
train_labels = th.tensor(y_train)
test_inputs = th.tensor(X_test,dtype=th.float)
test_labels = th.tensor(y_test)

# Send the training and test data to the gatways in equal proportion.
# since there are two gateways we are splitting into two : 
train_idx = int(len(train_labels)/2)
test_idx = int(len(test_labels)/2)
gateway1_train_dataset = sy.BaseDataset(train_inputs[:train_idx], train_labels[:train_idx]).send(gateway1)
gateway2_train_dataset = sy.BaseDataset(train_inputs[train_idx:], train_labels[train_idx:]).send(gateway2)
gateway1_test_dataset = sy.BaseDataset(test_inputs[:test_idx], test_labels[:test_idx]).send(gateway1)
gateway2_test_dataset = sy.BaseDataset(test_inputs[test_idx:], test_labels[test_idx:]).send(gateway2)

# Create federated datasets, an extension of Pytorch TensorDataset class
federated_train_dataset = sy.FederatedDataset([gateway1_train_dataset, gateway2_train_dataset])
federated_test_dataset = sy.FederatedDataset([gateway1_test_dataset, gateway2_test_dataset])

# Create federated dataloaders, an extension of Pytorch DataLoader class
federated_train_loader = sy.FederatedDataLoader(federated_train_dataset, shuffle=True, batch_size=BATCH_SIZE)
federated_test_loader = sy.FederatedDataLoader(federated_test_dataset, shuffle=False, batch_size=BATCH_SIZE)

"""**Constructing Neural Network**"""

import torch.nn as nn
class Net(nn.Module):
    def __init__(self, input_dim, output_dim):
        """
        input_dim: number of input features.
        output_dim: number of labels.
        """
        super(Net, self).__init__()
        self.linear = th.nn.Linear(input_dim, output_dim)
    def forward(self, x):
        outputs = self.linear(x)
        return outputs

"""**Training Using Neural Network**"""

import torch.nn.functional as F

def train(model, device, federated_train_loader, optimizer, epoch):
    model.train()
    # Iterate through each gateway's dataset
    for idx, (data, target) in enumerate(federated_train_loader):
        batch_idx = idx+1
        # Send the model to the right gateway
        model.send(data.location)
        # Move the data and target labels to the device (cpu/gpu) for computation
        data, target = data.to(device), target.to(device)
        # Clear previous gradients (if they exist)
        optimizer.zero_grad()
        # Make a prediction
        output = model(data)
        # Calculate the cross entropy loss [We are doing classification]
        loss = F.cross_entropy(output, target)
        # Calculate the gradients
        loss.backward()
        # Update the model weights
        optimizer.step()
        # Get the model back from the gateway
        model.get()
        if batch_idx==len(federated_train_loader) or (batch_idx!=0 and batch_idx % LOG_INTERVAL == 0):
            # get the loss back
            loss = loss.get()
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * BATCH_SIZE, len(federated_train_loader) * BATCH_SIZE,
                100. * batch_idx / len(federated_train_loader), loss.item()))

def test(model, device, federated_test_loader):
    model.eval()
    correct = 0
    with th.no_grad():
        for batch_idx, (data, target) in enumerate(federated_test_loader):
            # Send the model to the right gateway
            model.send(data.location)
            # Move the data and target labels to the device (cpu/gpu) for computation
            data, target = data.to(device), target.to(device)
            # Make a prediction
            output = model(data)
            # Get the model back from the gateway
            model.get()
            # Calculate the cross entropy loss
            loss = F.cross_entropy(output, target)
            # Get the index of the max log-probability 
            pred = output.argmax(1, keepdim=True)
            # Get the number of instances correctly predicted
            correct += pred.eq(target.view_as(pred)).sum().get()
                
    # get the loss back
    loss = loss.get()
    print('Test set: Loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        loss.item(), correct, len(federated_test_loader.federated_dataset),
        100. * correct / len(federated_test_loader.federated_dataset)))

# Commented out IPython magic to ensure Python compatibility.
# %%time
# import torch.optim as optim
# 
# # Initialize the model
# model = Net(n_feature,n_class)
# 
# #Initialize the SGD optimizer
# optimizer = optim.SGD(model.parameters(), lr=lr)
# 
# for epoch in range(1, 5 + 1):
#     # Train on the training data in a federated way
#     train(model, device, federated_train_loader, optimizer, epoch)
#     # Check the test accuracy on unseen test data in a federated way
#     test(model, device, federated_test_loader)

from google.colab import files
# Save the model
th.save(model.state_dict(), "network-threat-kaggle-model.pt")
#Download Model
files.download('network-threat-kaggle-model.pt')
# Reload the model in a new model object
model_new = Net(n_feature,n_class)
model_new.load_state_dict(th.load("network-threat-kaggle-model.pt"))
model_new.eval()

# Take the 122th record from the test data
idx = 122
data = test_inputs[idx]
pred = model_new(data)
pred_label = int(pred.argmax().data.cpu().numpy())
pred_threat = encoder.inverse_transform([pred_label])[0]
print("Predicted threat type : ", pred_threat)
actual_label = int(test_labels[idx].data.cpu().numpy())
actual_threat = encoder.inverse_transform([actual_label])[0]
print("Actual threat type : ", actual_threat)