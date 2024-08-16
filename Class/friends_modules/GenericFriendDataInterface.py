from abc import ABC, abstractmethod

class GenericFriendDataInterface(ABC):
    
    @abstractmethod
    def load(self) -> dict:
        """
        returns dict of {"id": FriendClass, ...}
        """
        pass
    
    @abstractmethod
    def save(self, dict_to_save):
        pass
    
    @abstractmethod
    def update(self):
        pass
    