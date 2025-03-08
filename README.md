# Power switch customized
 Compare electricity fee based on personal electricity usage history between different electricity plans in New Zealand

![dependencies Python 3.12](https://shields.io/badge/dependencies-Python_3.12-blue)

## Install

Create a Python virtual environment and activate.

Set the program's root directory as the current directory.

Go to https://djecrety.ir/ and generate a secret key.

Create a file `token.json`, and write the following content.

```
{
    "secret_key": "$secret_key"
}
```

where `$secret_key` is the key you just generated.

Run the following command.

```
pip install -r requirements.txt
python manage.py migrate
```



## Usage

Run the following command.

```
python manage.py runserver
```

Open the browser and visit http://127.0.0.1:8000/ 

