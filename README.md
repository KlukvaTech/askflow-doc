# Askflow-doc
## Usage
Downloading linux dependencies:
```sh
sudo chmod +x starter
./starter
```

```sh
pip install -e .
```

or

```sh
pip install .
```

The app requires the Haystack RESTful API to be ready and accepting connections at `http://localhost:8000`, you can use Docker compose to start only the required containers:

```sh
sudo docker-compose up elasticsearch haystack-api
```

```
streamlit run ui/webapp.py
```
