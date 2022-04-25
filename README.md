# SS2PL • SiteShield to PrefixList
[![Code style](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/python/black) [![License](https://img.shields.io/github/license/vladvasiliu/ss2pl)](LICENSE)


`ss2pl` is a small script that updates the rules of an AWS Prefix List to match the IPs of an Akamai SiteShield Map.


## Functional description


The program does the following actions:

* Retrieve the list of SiteShield Maps from Akamai
* Only process the maps which:
  1. Are not acknowledged
  2. Have an entry in the program's configuration
* For each of the processed maps, do the following:
  1. If the list of proposed CIDRs is empty, skip it and log a warning.
  2. Compute the new IPs to add
  3. Compute the old IPs to remove
  4. Update the prefix list
  5. Acknowledge the SiteShield Map change if the Prefix List update was successful.


## Usage

### Configuration

Configuration is read from an AWS Secret. The program must be told how to reach that secret either through ENV vars or
through an `.env` file, located in the CWD:

```bash
   AWS_SECRET_NAME=some_secret/dev
   AWS_SECRET_REGION=us-east-1
   AWS_PROFILE=some_aws_profile   # this is optional
```

The configuration is expected to be valid JSON (it's parsed by Python's
[`json.loads`](https://docs.python.org/3/library/json.html#json.loads) function).

The following is the expected layout:

* `akamai`: Akamai-related configuration object. The fields can be obtained from Akamai identity page
   - `access_token`
   - `client_token`
   - `client_secret`
   - `host`: must start with a scheme, usually ``https://``
* `ss_to_pl`: A mapping of SiteShield Map ids to AWS Prefix List Definitions
   - `<site_shield_map_id>`:
      + `name`: a PrefixList name, used for logging purposes
      + `prefix_list_id`: the AWS Prefix List id, as defined on AWS
      + `description` *optional*: description to add to the PrefixList rules, defaults to *SiteShield* if empty
      + `region_name`: AWS region where the PrefixList lives
      + `account` *optional*: object describing an AWS account if the PrefixList isn't in the base account
         - `name`: AWS Account name, used for logging purposes
         - `id`: The 12-digit ID of the account
         - `role_name`: the name of the role to be assumed

Example JSON config:

```json
{
  "akamai": {
    "client_secret": "=_akamai_client_secret_=",
    "host": "https://akab-some-host-name.luna.akamaiapis.net",
    "access_token": "akab-some-access-token",
    "client_token": "akab-some-client-token"
  },
  "ss_to_pl": {
    "1234567": {
        "name": "Prefix List Name",
        "prefix_list_id": "pl-1234567890abdefab",
        "region_name": "eu-west-3",
        "account": {
          "name": "some-account-name",
          "id": 123456789012,
          "role_name": "role-name-to-assume"
        }
      }
  }
}
```

### AWS Policies

In order to function, the program needs to be able to call the relevant AWS APIs, namely those centered around EC2
Prefix Lists. This authorisation has to be added to any role that will be used to interact with a Prefix List.
Below is an example of a minimal policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeManagedPrefixLists",
                "ec2:GetManagedPrefixListEntries",
                "ec2:ModifyManagedPrefixList"
            ],
            "Resource": "arn:aws:ec2:eu-west-3:123456789123:prefix-list/pl-0123456789abcdef0"
        }
    ]
}
```

The program will also need to be able to read its configuration from AWS Secret Manager. This has to be added to the
base role. Example:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VisualEditor0",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
        "secretsmanager:ListSecretVersionIds"
      ],
      "Resource": "arn:aws:secretsmanager:eu-west-3:123456789012:secret:super-secret/dev-*"
    }
  ]
}
```

### Akamai

On Akamai you'll have to create an API client. As this application shouldn't be tied to a particular human user, I'd
recommend creating a new *API Service Account*. This client can then have multiple "Authorized users" who may manage it.

You'll need to create a new *Client Token* and fetch the *client secret*.

The program requires *read-write* level access to the *SiteShield API*. Write is required for acknowledging the change.
You'll also have to add the Editor Role for the groups containing the SiteShield APIs you want to manage.

## Limitations

As this is made mainly for my own use, there are some limitations. Namely:

* Only one set of Akamai credentials can be loaded at a time. If you need multiple Akamai credentials, you'll have to
    run multiple instances.
* Only one Managed Prefix List per Site Shield Map is supported.
* The program is expected to run on AWS using an Instance/Task role as the starting point for authentication to AWS.
  In case the program runs somewhere else, there is basic support for the AWS_PROFILE environment variable.
  If this variable is used, it expects to find the credentials in the usual places.
  Refer to the [AWS Docs](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html)
  for more information.
* It doesn't attempt to be smart, so you may configure the same Prefix List multiple times.
  It will then be modified multiple times.

## License

This program is distributed under the terms of the [3-Clause BSD License](LICENSE).


## Useful documentation

### Akamai

* [API Identity model](https://developer.akamai.com/legacy/introduction/Identity_Model.html)
* [API Client authentication](https://developer.akamai.com/legacy/introduction/Client_Auth.html)
* [Site Shield API v1](https://developer.akamai.com/api/cloud_security/site_shield/v1.html)
* [EdgeGrid for Python](https://github.com/akamai/AkamaiOPEN-edgegrid-python)
