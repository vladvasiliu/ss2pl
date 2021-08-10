#####
SS2SG
#####

|Status badge| |Style badge| |License badge|

***************************
SiteShield to SecurityGroup
***************************

``ss2sg`` is a small script that updates the rules of an AWS Security Group to match the IPs of an Akamai SiteShield Map.

=====
Usage
=====

-------------
Configuration
-------------

Configuration is read from an AWS Secret. The program must be told how to reach that secret either through ENV vars or
through an `.env` file, located in the CWD.

.. code-block:: bash
   :caption: example .env file

    AWS_SECRET_NAME=some_secret/dev
    AWS_SECRET_REGION=eu-east-1
    AWS_PROFILE_NAME=some_aws_profile   # this is optional

The configuration is expected to be valid JSON (it's parsed by Python's `json.loads` function).

The following is the expected layout:

* `akamai`: Akamai-related configuration object. The fields can be obtained from Akamai identity page
   * `access_token`
   * `client_token`
   * `client_secret`
   * `host`: must start with a scheme, usually `https://`
* `ss_map_to_sg_mapping`: A mapping of SiteShield Map ids to lists of AWS Security Group Definitions
   * `site_shield_map_id`:
      * `name`: a SecurityGroup name, used for logging purposes
      * `group_id`: the AWS SecurityGroup id, as defined on AWS
      * `protocol`: the protocol of the rules to be handled
      * `from_port`: the starting port of the rule
      * `to_port` *optional*: the ending port of the range; if any, only one port (`from_port`) will be authorized
      * `description` *optional*: description to add to the SecurityGroup rules, defaults to *SiteShield* if empty
      * `region_name`: AWS region where the SecurityGroup lives
      * `account` *optional*: object describing an AWS account if the SecurityGroup isn't in the base account
         * `name`: AWS Account name, used for logging purposes
         * `id`: The 12-digit ID of the account
         * `role_name`: the name of the role to be assumed

.. code-block:: json
   :caption: example AWS secret
   :linenos:

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


=======
License
=======

This program is distributed under the terms of the `3-Clause BSD License <LICENSE>`_.


====================
Useful documentation
====================

Akamai
------

* `API Identity model <https://developer.akamai.com/legacy/introduction/Identity_Model.html>`_
* `API Client authentication <https://developer.akamai.com/legacy/introduction/Client_Auth.html>`_
* `Site Shield API v1 <https://developer.akamai.com/api/cloud_security/site_shield/v1.html>`_
* `EdgeGrid for Python <https://github.com/akamai/AkamaiOPEN-edgegrid-python>`_



.. |Style badge| image:: https://img.shields.io/badge/code%20style-black-000000
   :target: https://github.com/python/black
.. |License badge| image:: https://img.shields.io/github/license/vladvasiliu/ss2sg
   :target: LICENSE
.. |Status badge| image:: https://img.shields.io/badge/status-pre--alpha-red
