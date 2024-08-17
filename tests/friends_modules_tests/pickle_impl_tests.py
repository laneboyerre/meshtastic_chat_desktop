import unittest

from Class.friends_modules.PickleFriendInterfaceImpl import PickleFriendInterface
from Class.friends_modules.friend import Friend
import os

class TestPickleImpl(unittest.TestCase):

    def test_reading_and_writing(self):
        testing_location = os.path.dirname(__file__)
        impl = PickleFriendInterface(testing_location)
        
        friends_dict = {
            'abc':
                Friend('abc'),
            'def':
                Friend('def')
        }
        
        impl.save(friends_dictionary=friends_dict)
        
        self.assertTrue(os.path.isfile(testing_location + "/friends.pickle"))
        
        loaded_friends_dict = impl.load()
        
        for k, v in loaded_friends_dict.items():
            self.assertEqual(loaded_friends_dict[k],
                             friends_dict[k])
        os.remove(testing_location + "/friends.pickle")
        
        
if __name__ == '__main__':
    unittest.main()