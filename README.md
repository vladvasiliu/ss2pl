# SS2SG • SiteShield to SecurityGroup
[![Code style](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/python/black) [![License](https://img.shields.io/github/license/vladvasiliu/ss2sg)](LICENSE)


`ss2sg` is a small script that updates the rules of an AWS Security Group to match the IPs of an Akamai SiteShield Map.


## Functional description


The program does the following actions:

* Retrieve the list of SiteShield Maps from Akamai
* Only process the maps which:
  1. Are not acknowledged
  2. Have an entry in the program's configuration
* For each of the processed maps, do the following:
  1. If the list of proposed CIDRs is empty, skip it and log a warning.
  2. For each of the map's security groups:
     1. Compute the new IPs to authorize
     2. Compute the old IPs to revoke
     3. Authorize the new IPs
     4. Revoke the old IPs
  3. Acknowledge the SiteShield Map change if no failure happened for any of its Security Groups. Otherwise, don't
     acknowledge and log a warning.


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
* `ss_map_to_sg_mapping`: A mapping of SiteShield Map ids to lists of AWS Security Group Definitions
   - `site_shield_map_id`:
      + `name`: a SecurityGroup name, used for logging purposes
      + `group_id`: the AWS SecurityGroup id, as defined on AWS
      + `protocol`: the protocol of the rules to be handled
      + `from_port`: the starting port of the rule
      + `to_port` *optional*: the ending port of the range; if none, only one port (`from_port`) will be authorized
      + `description` *optional*: description to add to the SecurityGroup rules, defaults to *SiteShield* if empty
      + `region_name`: AWS region where the SecurityGroup lives
      + `account` *optional*: object describing an AWS account if the SecurityGroup isn't in the base account
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
  "ss_map_to_sg_mapping": {
    "1234567": [
      {
        "name": "SecurityGroupName",
        "group_id": "sg-1234567890abdefab",
        "protocol": "tcp",
        "from_port": 123,
        "region_name": "eu-west-3",
        "account": {
          "name": "some-account-name",
          "id": 123456789012,
          "role_name": "role-name-to-assume"
        }
      }
    ]
  }
}
```

### AWS Policies

In order to function, the program needs to be able to call the relevant AWS APIs, namely those centered around EC2
Security Groups. This authorisation has to be added to any role that will be used to interact with a Security Group.
Below is an example of a minimal policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VisualEditor0",
      "Effect": "Allow",
      "Action": [
        "ec2:RevokeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupIngress"
      ],
      "Resource": "arn:aws:ec2:eu-west-3:123456789012:security-group/sg-1234567890abcdef1"
    },
    {
      "Sid": "VisualEditor1",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeSecurityGroupRules",
        "ec2:DescribeSecurityGroups"
      ],
      "Resource": "*"
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
* There is rudimentary support for multiple Security Groups per Akamai SiteShield Map.
  In case updating any of them fails, the map change will not be acknowledged and changes that were made won't be rolled
  back.
* The program is expected to run on AWS using an Instance/Task role as the starting point for authentication to AWS.
  In case the program runs somewhere else, there is basic support for the AWS_PROFILE environment variable.
  If this variable is used, it expects to find the credentials in the usual places.
  Refer to the [AWS Docs](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html)
  for more information.
* It doesn't attempt to be smart, so you may configure the same security group multiple times. The security group
  will then be modified multiple times.
* The program expects to be the only entity interacting with the configured Security Groups. It will remove any rules
  that don't correspond to the Akamai SiteShield Maps!
* There's no AWS API that allows authorizing and revoking Security Group rules in a same call, so the rule change is not
  atomic. The program may therefore be able to authorize new IPs but fail to revoke old ones.

## License

This program is distributed under the terms of the [3-Clause BSD License](LICENSE).


## Useful documentation

### Akamai

* [API Identity model](https://developer.akamai.com/legacy/introduction/Identity_Model.html)
* [API Client authentication](https://developer.akamai.com/legacy/introduction/Client_Auth.html)
* [Site Shield API v1](https://developer.akamai.com/api/cloud_security/site_shield/v1.html)
* [EdgeGrid for Python](https://github.com/akamai/AkamaiOPEN-edgegrid-python)
