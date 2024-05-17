import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from src.utils import *

PRINT_EACH = 500

## MS2


class MLP(nn.Module):
    """
    An MLP network which does classification.

    It should not use any convolutional layers.
    """

    def __init__(self, input_size, n_classes):
        """
        Initialize the network.
        
        You can add arguments if you want, but WITH a default value, e.g.:
            __init__(self, input_size, n_classes, my_arg=32)
        
        Arguments:
            input_size (int): size of the input
            n_classes (int): number of classes to predict
        """
        super().__init__()
        self.mlp = nn.Sequential(
            # Linear block 1
            nn.Linear(input_size, 128      , bias=True),
            nn.ReLU(),
            # Linear block 2
            nn.Linear(128       , 64      , bias=True),
            nn.ReLU(),
            #Linear block 3
            nn.Linear(64       , 32      , bias=True),
            nn.ReLU(),
            ## linear block 4
            nn.Linear(32       , n_classes, bias=True)
        )

    def forward(self, x):
        """
        Predict the class of a batch of samples with the model.

        Arguments:
            x (tensor): input batch of shape (N, D)
        Returns:
            preds (tensor): logits of predictions of shape (N, C)
                Reminder: logits are value pre-softmax.
        """
        preds = self.mlp(x)

        return preds


class CNN(nn.Module):
    """
    A CNN which does classification.

    It should use at least one convolutional layer.
    """

    def __init__(self, input_channels, n_classes):
        """
        Initialize the network.
        
        You can add arguments if you want, but WITH a default value, e.g.:
            __init__(self, input_channels, n_classes, my_arg=32)
        
        Arguments:
            input_channels (int): number of channels in the input
            n_classes (int): number of classes to predict
        """
        super().__init__()
        self.cnn = nn.Sequential(
            # Conv block 1  (-> output: (8, 14, 14))
            nn.Conv2d(input_channels, 8, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
        
            # Conv block 2  (-> output: (16, 7, 7))
            nn.Conv2d(8, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
        
            #Conv block 3  (-> output: (32, 4, 4))
            nn.Conv2d(16, 32, kernel_size=3, padding=2),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
        
            # Flatten to a vector before feeding it to the mlp
            nn.Flatten(-3),
        
            # MLP block 1
            nn.Linear(32 * 4 * 4, 256, bias=True),
            nn.ReLU(),
            
            # MLP block 2
            nn.Linear(256, 128, bias=True),
            nn.ReLU(),
            
            # MLP block 3
            nn.Linear(128, n_classes, bias=True)
        )

    def forward(self, x):
        """
        Predict the class of a batch of samples with the model.

        Arguments:
            x (tensor): input batch of shape (N, Ch, H, W)
        Returns:
            preds (tensor): logits of predictions of shape (N, C)
                Reminder: logits are value pre-softmax.
        """
        preds = self.cnn(x)

        return preds


class MyViT(nn.Module):
    """
    A Transformer-based neural network
    """

    def __init__(self, chw, n_patches, n_blocks, hidden_d, n_heads, out_d):
        """
        Initialize the network.
        
        """
        super().__init__()
        self.chw = chw # (C, H, W)
        self.n_patches = n_patches
        self.n_blocks = n_blocks
        self.n_heads = n_heads
        self.hidden_d = hidden_d

        # Input and patches sizes
        assert chw[1] % n_patches == 0 # Input shape must be divisible by number of patches
        assert chw[2] % n_patches == 0
        self.patch_size = (chw[1] / n_patches, chw[2] / n_patches)

        # Linear mapper
        self.input_d = int(chw[0] * self.patch_size[0] * self.patch_size[1])
        self.linear_mapper = nn.Linear(self.input_d, self.hidden_d)

        # Learnable classification token
        self.class_token = nn.Parameter(torch.rand(1, self.hidden_d))

        # Positional embedding
        # HINT: don't forget the classification token
        self.positional_embeddings =  get_positional_embeddings(n_patches ** 2 + 1, hidden_d)

        # Transformer blocks
        self.blocks = nn.ModuleList([MyViTBlock(hidden_d, n_heads) for _ in range(n_blocks)])

        # Classification MLP
        self.mlp = nn.Sequential(
            nn.Linear(self.hidden_d, out_d),
            nn.Softmax(dim=-1)
        )

    def forward(self, x):
        """
        Predict the class of a batch of samples with the model.

        Arguments:
            x (tensor): input batch of shape (N, Ch, H, W)
        Returns:
            preds (tensor): logits of predictions of shape (N, C)
                Reminder: logits are value pre-softmax.
        """
        n, c, h, w = x.shape

        # Divide images into patches.
        patches = patchify(x, self.n_patches)

        # Map the vector corresponding to each patch to the hidden size dimension.
        tokens = self.linear_mapper(patches)

        # Add classification token to the tokens.
        tokens = torch.cat((self.class_token.expand(n, 1, -1), tokens), dim=1)

        # Add positional embedding.
        # HINT: use torch.Tensor.repeat(...)
        out = tokens + self.positional_embeddings.repeat(n, 1, 1)

        # Transformer Blocks
        for block in self.blocks:
            out = block(out)

        # Get the classification token only.
        out = out[:, 0]

        # Map to the output distribution.
        preds = self.mlp(out)

        

        return preds


class Trainer(object):
    """
    Trainer class for the deep networks.

    It will also serve as an interface between numpy and pytorch.
    """

    def __init__(self, model, lr, epochs, batch_size):
        """
        Initialize the trainer object for a given model.

        Arguments:
            model (nn.Module): the model to train
            lr (float): learning rate for the optimizer
            epochs (int): number of epochs of training
            batch_size (int): number of data points in each batch
        """
        self.lr = lr
        self.epochs = epochs
        self.model = model
        self.batch_size = batch_size

        self.criterion = nn.CrossEntropyLoss()
        self.optimizer = torch.optim.SGD(model.parameters(), lr=lr)

    def train_all(self, dataloader):
        """
        Fully train the model over the epochs. 
        
        In each epoch, it calls the functions "train_one_epoch". If you want to
        add something else at each epoch, you can do it here.

        Arguments:
            dataloader (DataLoader): dataloader for training data
        """
        for ep in range(self.epochs):
            self.train_one_epoch(dataloader, ep)


    def train_one_epoch(self, dataloader, ep):
        """
        Train the model for ONE epoch.

        Should loop over the batches in the dataloader. (Recall the exercise session!)
        Don't forget to set your model to training mode, i.e., self.model.train()!

        Arguments:
            dataloader (DataLoader): dataloader for training data
        """
        self.model.train()
        running_loss = 0
        for iter, batch in enumerate(dataloader):
            inputs, labels = batch
            #zero gradients
            self.optimizer.zero_grad()

            # fwd + bwd + optimize
            logists = self.model(inputs)
            loss = self.criterion(logists, labels)
            running_loss += loss.item()
            loss.backward()
            self.optimizer.step()

            if iter % PRINT_EACH == PRINT_EACH-1:
                print(f"[{ep+1}, {iter+1:5d}] average_loss: {running_loss/PRINT_EACH}")
                running_loss = 0

    def predict_torch(self, dataloader):
        """
        Predict the validation/test dataloader labels using the model.

        Hints:
            1. Don't forget to set your model to eval mode, i.e., self.model.eval()!
            2. You can use torch.no_grad() to turn off gradient computation, 
            which can save memory and speed up computation. Simply write:
                with torch.no_grad():
                    # Write your code here.

        Arguments:
            dataloader (DataLoader): dataloader for validation/test data
        Returns:
            pred_labels (torch.tensor): predicted labels of shape (N,),
                with N the number of data points in the validation/test data.
        """
        self.model.eval()
        pred_labels = []
        with torch.no_grad():
            for inputs in dataloader:
                outputs = self.model(inputs[0])
                pred_labels.append(outputs)
        pred_labels = torch.cat(pred_labels)
        
        return onehot_to_label(F.softmax(pred_labels, dim=1))
    
    def fit(self, training_data, training_labels):
        """
        Trains the model, returns predicted labels for training data.

        This serves as an interface between numpy and pytorch.

        Arguments:
            training_data (array): training data of shape (N,D)
            training_labels (array): regression target of shape (N,)
        Returns:
            pred_labels (array): target of shape (N,)
        """
        N, D = training_data.shape
        W = H = int(np.sqrt(D))
        if isinstance(self.model, CNN):
            # add number of channels
            assert W * H == D
            training_data_reshaped = training_data.reshape(N, 1, W, H)
        elif isinstance(self.model, MLP):
            training_data_reshaped = training_data
        elif isinstance(self.model, MyViT):
            assert W * H == D
            training_data_reshaped = training_data.reshape(N, 1, W, H)

        # transform target to one hot independently of the model
        training_labels = label_to_onehot(training_labels)
        train_dataset = TensorDataset(torch.from_numpy(training_data_reshaped).float(), 
                                      torch.from_numpy(training_labels))
        train_dataloader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)
        
        self.train_all(train_dataloader)

        return self.predict(training_data)

    def predict(self, test_data):
        """
        Runs prediction on the test data.

        This serves as an interface between numpy and pytorch.
        
        Arguments:
            test_data (array): test data of shape (N,D)
        Returns:
            pred_labels (array): labels of shape (N,)
        """
        N, D = test_data.shape
        W = H = int(np.sqrt(D))
        if isinstance(self.model, CNN):
            # add number of channels
            assert W * H == D
            test_data = test_data.reshape(N, 1, W, H)
        elif isinstance(self.model, MLP):
            # nothing to be done input already has correct shape
            pass
        elif isinstance(self.model, MyViT):
            assert W * H == D
            test_data = test_data.reshape(N, 1, W, H)
        # First, prepare data for pytorch
        test_dataset = TensorDataset(torch.from_numpy(test_data).float())
        test_dataloader = DataLoader(test_dataset, batch_size=self.batch_size, shuffle=False)

        pred_labels = self.predict_torch(test_dataloader)

        # We return the labels after transforming them into numpy array.
        return pred_labels.cpu().numpy()A&
    
def patchify(images, n_patches):
    n, c, h, w = images.shape

    assert h == w # We assume square image.

    patches = torch.zeros(n, n_patches ** 2, h * w * c // n_patches ** 2)
    patch_size = h // n_patches

    for idx, image in enumerate(images):
        for i in range(n_patches):
            for j in range(n_patches):

                # Extract the patch of the image.
                patch = image[:, i * patch_size: (i + 1) * patch_size, j * patch_size: (j + 1) * patch_size] ### WRITE YOUR CODE HERE

                # Flatten the patch and store it.
                patches[idx, i * n_patches + j] = patch.flatten() ### WRITE YOUR CODE HERE
    return patches

def get_positional_embeddings(sequence_length, d):
    result = torch.ones(sequence_length, d)
    for i in range(sequence_length):
        for j in range(d):
            ### WRITE YOUR CODE HERE
            if j % 2 == 0:
                result[i, j] = np.sin(i/(10000**(j/d)))
            else :
                result[i, j] = np.cos(i/(10000**((j-1)/d)))
    return result

def get_positional_embeddings(sequence_length, d):
    result = torch.ones(sequence_length, d)
    for i in range(sequence_length):
        for j in range(d):
            ### WRITE YOUR CODE HERE
            if j % 2 == 0:
                result[i, j] = np.sin(i/(10000**(j/d)))
            else :
                result[i, j] = np.cos(i/(10000**((j-1)/d)))
    return result

class MyMSA(nn.Module):
    def __init__(self, d, n_heads=2):
        super(MyMSA, self).__init__()
        self.d = d
        self.n_heads = n_heads

        assert d % n_heads == 0, f"Can't divide dimension {d} into {n_heads} heads"
        d_head = int(d / n_heads)
        self.d_head = d_head

        self.q_mappings = nn.ModuleList([nn.Linear(d_head, d_head) for _ in range(self.n_heads)])
        self.k_mappings = nn.ModuleList([nn.Linear(d_head, d_head) for _ in range(self.n_heads)])
        self.v_mappings = nn.ModuleList([nn.Linear(d_head, d_head) for _ in range(self.n_heads)])

        self.softmax = nn.Softmax(dim=-1)

    def forward(self, sequences):
        result = []
        for sequence in sequences:
            seq_result = []
            for head in range(self.n_heads):

                # Select the mapping associated to the given head.
                q_mapping = self.q_mappings[head]
                k_mapping = self.k_mappings[head]
                v_mapping = self.v_mappings[head]

                seq = sequence[:, head * self.d_head: (head + 1) * self.d_head]

                # Map seq to q, k, v.
                q, k, v = q_mapping(seq), k_mapping(seq), v_mapping(seq)

                attention = q @ k.T / np.sqrt(self.d_head)
                seq_result.append(attention @ v)
            result.append(torch.hstack(seq_result))
        return torch.cat([torch.unsqueeze(r, dim=0) for r in result])

class MyViTBlock(nn.Module):
    def __init__(self, hidden_d, n_heads, mlp_ratio=4):
        super(MyViTBlock, self).__init__()
        self.hidden_d = hidden_d
        self.n_heads = n_heads

        self.norm1 = nn.LayerNorm(hidden_d)
        self.mhsa = MyMSA(hidden_d, n_heads) ### WRITE YOUR CODE HERE
        self.norm2 = nn.LayerNorm(hidden_d)
        self.mlp = nn.Sequential( ### WRITE YOUR CODE HERE
            nn.Linear(hidden_d, mlp_ratio * hidden_d),
            nn.GELU(),
            nn.Linear(mlp_ratio * hidden_d, hidden_d)
        )

    def forward(self, x):
        # Write code for MHSA + residual connection.
        out = x + self.mhsa(self.norm1(x))
        # Write code for MLP(Norm(out)) + residual connection
        out = out + self.mlp(self.norm2(out))
        return out
