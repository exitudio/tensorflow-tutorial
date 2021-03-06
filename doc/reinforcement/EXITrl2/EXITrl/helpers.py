from collections import deque
import random
import torch
import numpy as np
from gym.spaces.box import Box
from gym.spaces.discrete import Discrete

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_simple_model(num_input, num_hidden, num_output):
    return torch.nn.Sequential(
        torch.nn.Linear(num_input, num_hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(num_hidden, num_output)
    )


def print_weight_size(model):
    for name, param in model.named_parameters():
        if param.requires_grad and "weight" in name:
            print(name, param.data.shape)


def copy_params(from_model, to_model):
    for from_param, to_param in zip(from_model.parameters(), to_model.parameters()):
        to_param.data.copy_(from_param.data)


def update_params(from_model, to_model, tau):
    for from_param, to_param in zip(from_model.parameters(), to_model.parameters()):
        update_data = tau*from_param.data + (1-tau) * to_param.data
        to_param.data.copy_(update_data)


def convert_to_tensor(input):
    if type(input) is np.ndarray:
        input = torch.from_numpy(input).float().to(device)
    else:
        input = torch.FloatTensor(input).to(device)
    return input


def get_state_action_shape_from_env(env):
    # state
    if isinstance(env.observation_space, Discrete):
        state_shape = [env.observation_space.n]
    elif isinstance(env.observation_space, Box):
        state_shape = env.observation_space.shape[0]

    # action
    if isinstance(env.action_space, Discrete):
        action_shape = env.action_space.n
    elif isinstance(env.action_space, Box):
        action_shape = env.action_space.shape[0]

    return state_shape, action_shape


class MeanBuffer:
    """ Use to calculate mean rewards"""

    def __init__(self, capacity):
        self.capacity = capacity
        self.deque = deque(maxlen=capacity)
        self.sum = 0.0

    def add(self, val):
        if len(self.deque) == self.capacity:
            self.sum -= self.deque[0]
        self.deque.append(val)
        self.sum += val

    def mean(self):
        if not self.deque:
            return 0.0
        return self.sum / len(self.deque)


class WeightDecay:
    def __init__(self, start, end, decay):
        self.val = start
        self.end = end
        self.decay = decay

    def step(self):
        self.val = max(self.end, self.decay*self.val)
        return self.val


class ExperienceReplay2:
    # save as np array but return as tensor
    def __init__(self, num_experience=128, num_recall=64):
        self.num_experience = int(num_experience)
        self.num_recall = int(num_recall)
        self.memories = []
        self.position = 0
        self.num_current_experience = 0

    def remember(self, *transition):
        if self.num_current_experience == 0:
            for i, var in enumerate(transition):
                isListOrTuble = isinstance(var, (list, tuple, np.ndarray))
                if isListOrTuble:
                    shape = list(
                        num_shape for num_shape in np.array(var).shape)
                    shape.insert(0, self.num_experience)
                else:
                    shape = self.num_experience
                # generate empty np array supporting deep list
                self.memories.append(np.empty(shape))
        for i, _ in enumerate(self.memories):
            self.memories[i][self.position] = np.array(transition[i])

        self.position = (self.position + 1) % self.num_experience
        if (self.num_current_experience < self.num_experience):
            self.num_current_experience += 1

    def recall(self):
        # in the case that data is still not full yet.
        num_sample = self.num_current_experience if self.num_recall > self.num_current_experience else self.num_recall
        indexes = random.sample(range(self.num_current_experience), num_sample)
        return tuple(torch.tensor(i[indexes].astype(float), dtype=torch.float, device=device) for i in self.memories)


class ExperienceReplay:
    def __init__(self, num_experience=128, num_recall=64):
        self.num_experience = int(num_experience)
        self.num_recall = int(num_recall)
        self.memories = []
        self.position = 0
        self.num_current_experience = 0

    def remember(self, *args):
        if len(self.memories) == 0:
            # init
            for i in range(len(args)):
                self.memories.append(torch.tensor(
                    [args[i]], dtype=torch.float, device=device))
            self.num_current_experience += 1
        elif self.num_current_experience < self.num_experience:
            # less than max
            for i in range(len(args)):
                self.memories[i] = torch.cat(
                    (self.memories[i], torch.tensor([args[i]], dtype=torch.float, device=device)), dim=0)
            self.num_current_experience += 1
        else:
            # full experience. replace the existing ones
            for i in range(len(args)):
                self.memories[i][self.position] = torch.tensor(
                    [args[i]], dtype=torch.float, device=device)
            self.position = (self.position + 1) % self.num_experience

    def recall(self):
        memory_length = self.num_current_experience
        size = self.num_recall if self.num_recall < memory_length else memory_length
        query = random.sample(range(memory_length), size)
        return list([self.memories[i][query] for i in range(len(self.memories))])
