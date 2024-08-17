
class Friend():
    
    alias = ""
    
    def __init__(self, radio_id="") -> None:
        self.radio_id = radio_id
    
    def parse_selection_input(self, selection):
        mapped_values_list = ["N", "username", "radio_id", "AKA", "Hardware", "Latitude", "Longitude", "Battery", "Channel util.", "Tx air util.", "SNR", "Hops Away", "LastHeard", "Since"]
        for i in range(0, len(mapped_values_list)):
            setattr(self, mapped_values_list[i].lower(), selection['values'][i])
        
        return self
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        else:
            return False