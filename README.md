# Askflow-doc
## Usage
```sh
pip install -e .
```

The app requires the Haystack RESTful API to be ready and accepting connections at `http://localhost:8000`, you can use Docker compose to start only the required containers:

```sh
docker-compose up elasticsearch haystack-api
```

```
streamlit run ui/webapp.py
```
