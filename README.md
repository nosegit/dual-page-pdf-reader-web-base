# dual-page-pdf-reader-web-base
this project for manga dual page reader in webbase
- swap 2 pages from left-right to right-left
- toggle shift page for 1&2 to 2&3

## Working OS

| Operating System | Supported |
|------------------|-----------|
| Windows          | ✓         |
| macOS            | untest         |
| Linux            | ✓         |

# Usage
### with out conda
``` bash
    # install requirement package
    pip install -r requirement.txt

    # run script
    python pdf_reader_server.py

    # on browser
    127.0.0.1:5000 or ip_address:5000
```


### with conda
``` bash
    # setup conda
    conda create --name pdf_reader_server python=3.9

    # activate environment
    conda activate pdf_reader_server

    # install requirement package
    pip install -r requirement.txt

    # run script
    python pdf_reader_server.py

    # on browser
    127.0.0.1:5000 or ip_address:5000
    
```

### with docker
``` bash
    # build image 
    sudo docker build -t pdf_reader_server_docker .

    # run docker container
    sudo docker run -p 5000:5000 pdf_reader_server_docker

    # on browser
    127.0.0.1:5000 or ip_address:5000
```