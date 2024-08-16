import os
import json

from Class.friends_modules.GenericFriendDataInterface import GenericFriendDataInterface
class FriendsManager():
    
    friends_dictionary = {}
    
    def __init__(self, generic_friend_interface: GenericFriendDataInterface) -> None:
        self.backend_interface = generic_friend_interface
        self.friends_dictionary = generic_friend_interface.load()
    
    def add_friend(self, friend_object):
        self.friends_dictionary[friend_object.radio_id] = friend_object
        self.dump_and_save()
    
    def remove_friend(self, friend_object):
        if type(friend_object) == str:
            del self.friends_dictionary[friend_object]
        else:
            del self.friends_dictionary[friend_object.radio_id]
        self.dump_and_save()
    
    def dump_and_save(self):
        self.backend_interface.save(self.friends_dictionary)