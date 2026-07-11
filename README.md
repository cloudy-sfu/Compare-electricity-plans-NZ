# Compare electricity plans NZ
 Compare electricity fee based on personal electricity usage history between different electricity plans in New Zealand

![dependencies Python 3.13](https://shields.io/badge/dependencies-Python_3.13-blue)
![](https://shields.io/badge/dependencies-PowerShell_7-blue)

[Power switch](https://www.powerswitch.org.nz/) helps households compare residential electricity by estimating annual consumption based on typical usage profiles. However, its estimation is too general to capture the diverse and individualized electricity usage behaviors of different households, often leading to imprecise estimates. This program has the same objective as *power switch*, and tries to improve the accuracy by reading personal electricity usage history from the users' meter. It doesn't collect the list of electricity charging plans widely, but allows the user to manually add charging plans to compare.

**Contribution:** The program can only read electricity usage from the following companies.

- Contact Energy
- Mercury

If you can provide account of other electricity provider, or can write a web crawler to get data from other electricity provider, welcome to contribute.

<details>
    <summary>Gallery</summary>
    <img src="assets/Snipaste_2025-03-09_15-58-51.png" width="100%">
    <img src="assets/Snipaste_2025-03-09_15-59-14.png" width="100%">
    <img src="assets/Snipaste_2025-03-09_16-33-11.png" width="100%">
</details>

## Install

Create a PostgreSQL 17 database in [Neon](https://neon.com/) database, or your own PostgreSQL database.

Create `.env` file and define the following environment variables. [Format](https://github.com/env-lang/env/blob/main/env.md)

| Key        | Value                                                        |
| ---------- | ------------------------------------------------------------ |
| SECRET_KEY | Go to https://djecrety.ir/ and generate a secret key.        |
| NEON_DB    | Connection string to Neon database (or own PostgreSQL database). |

Create a Python virtual environment and activate.

Run the following command in PowerShell.

```
pip install -r requirements.txt
& .\set_env.ps1
python manage.py migrate
```

## Usage

Activate the Python virtual environment.

Run the following command in PowerShell.

```
& .\set_env.ps1
Start-Process "http://localhost:8000"
python manage.py runserver
```

You can find charging plans in electricity providers' websites or "power switch".

