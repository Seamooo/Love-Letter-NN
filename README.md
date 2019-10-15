Love-Letter-NN
==============
A basic neural network implementing the concepts of select - cross - mutate to generate the next generation

LoveLetterApi
------------
This project has been made compatible with the [java api](https://www.github.com/drtnf/LoveLetter) provided by Dr Tim French.  
The model is created using tensor flow and trains by interacting with the api via a java server that must be run before execution.
A future release will contain an agent capable of running the api just off saved model files.

Installation
------------
`pip3 install -r requirements.txt` to install 
run installer.py with `python3 installer.py` to install dependencies and compile java  
WARNING script will fail if jdk or svn are not in path  
[download](https://www.tensorflow.org/install/lang_java) and extract the jni for tensorflow appropriate to your system and place it in the Tensorflow-Config directory
`python3 start_server.py` to start the server  
then in a seperate shell `python3 train_agent.py` to train the model

Config
------
Currently hyperparameters are all manually set inside train_agent.py  
Support for custom hyperparameters and appropriate model identification is planned  


