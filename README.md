# Power switch customized
 Compare electricity fee based on personal electricity usage history between different electricity plans in New Zealand

![dependencies Python 3.12](https://shields.io/badge/dependencies-Python_3.12-blue)

[Power switch](https://www.powerswitch.org.nz/) helps households compare residential electricity by estimating annual consumption based on typical usage profiles. However, its estimation is too general to capture the diverse and individualized electricity usage behaviors of different households, often leading to imprecise estimates. This program has the same objective as *power switch*, and tries to improve the accuracy by reading personal electricity usage history from the users' meter. It doesn't collect the list of electricity charging plans widely, but allows the user to manually add charging plans to compare.

**Contribution: ** The program can only read electricity usage from the following list now. 

- Contact Energy

If you can provide account of other electricity provider, or can write a web crawler to get data from other electricity provider, welcome to contribute.

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

