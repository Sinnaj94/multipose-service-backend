import yaml

with open('app_config.yaml', 'r') as file:
    my_config = yaml.load(file, Loader=yaml.FullLoader)