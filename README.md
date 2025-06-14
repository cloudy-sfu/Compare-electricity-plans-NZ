# Compare electricity plans NZ
 Compare electricity fee based on personal electricity usage history between different electricity plans in New Zealand

![dependencies Python 3.12](https://shields.io/badge/dependencies-Python_3.12-blue)

[Power switch](https://www.powerswitch.org.nz/) helps households compare residential electricity by estimating annual consumption based on typical usage profiles. However, its estimation is too general to capture the diverse and individualized electricity usage behaviors of different households, often leading to imprecise estimates. This program has the same objective as *power switch*, and tries to improve the accuracy by reading personal electricity usage history from the users' meter. It doesn't collect the list of electricity charging plans widely, but allows the user to manually add charging plans to compare.

**Contribution:** The program can only read electricity usage from the following companies. 

- Contact

If you can provide account of other electricity provider, or can write a web crawler to get data from other electricity provider, welcome to contribute.

<details>
    <summary>Gallery</summary>
    <img src="assets/Snipaste_2025-03-09_15-58-51.png" width="100%">
    <img src="assets/Snipaste_2025-03-09_15-59-14.png" width="100%">
    <img src="assets/Snipaste_2025-03-09_16-33-11.png" width="100%">
</details>

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

You can find charging plans in the following pages. It's also an option to use *power switch* as an index and search the companies' official websites.

- [Contact](https://journey.contact.co.nz/residential/find-a-plan)
- [Genesis](https://www.genesisenergy.co.nz/join)
- [Powershop](https://www.powershop.co.nz/get-a-price/)
- [Mercury](https://www.mercury.co.nz/electricity?lcsp=1YEAR)
- [Flick](https://www.flickelectric.co.nz/)
- [Meridian](https://www.meridianenergy.co.nz/for-home)
