FROM continuumio/anaconda:latest
ADD . /app
WORKDIR /app

# Set up apt-get
RUN apt-get update -qq && apt-get install -yqq gnupg curl libgl1-mesa-glx gcc

# Install nodejs
RUN curl -sL https://deb.nodesource.com/setup_9.x | bash
RUN apt-get install -yqq nodejs
RUN apt-get clean -y

# Install sciris
RUN git clone https://github.com/optimamodel/sciris.git
RUN cd sciris && python setup.py develop

# Install mpld3
RUN git clone https://github.com/optimamodel/mpld3.git
RUN cd mpld3 && python setup.py submodule && python setup.py install

# Install atomica
RUN python setup.py develop

# Install clients common
WORKDIR clients
RUN python install_client.py

# Install cascade (TODO: add an option for cascade/tb)
WORKDIR cascade
RUN python build_client.py
