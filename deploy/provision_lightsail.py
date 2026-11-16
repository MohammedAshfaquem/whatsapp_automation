"""Provision the approved Wapp Lightsail instance in the explicitly selected account."""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.deployment-secrets'
REGION = 'ap-south-1'
ACCOUNT = '860892316390'
NAME = 'wapp-api-production'
KEY_NAME = 'wapp-production'


def aws(service, operation, **values):
    command = ['aws', service, operation, '--profile', 'default', '--region', REGION, '--output', 'json']
    if values:
        request = PRIVATE / f'{operation}.json'
        request.write_text(json.dumps(values), encoding='utf-8')
        command += ['--cli-input-json', f'file://{request}']
    return json.loads(subprocess.check_output(command, text=True))


def main():
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    if aws('sts', 'get-caller-identity')['Account'] != ACCOUNT:
        raise RuntimeError('Unexpected AWS account; no resources created.')
    instances = aws('lightsail', 'get-instances')['instances']
    if any(instance['name'] == NAME for instance in instances):
        raise RuntimeError('Instance already exists. Inspect it instead of creating another.')
    pem = PRIVATE / 'wapp-production.pem'
    if pem.exists():
        if not pem.read_text().startswith('-----BEGIN'):
            raise RuntimeError('Invalid existing SSH key; inspect before retrying.')
        aws('lightsail', 'get-key-pair', keyPairName=KEY_NAME)
    else:
        key = aws('lightsail', 'create-key-pair', keyPairName=KEY_NAME)
        private_key = key['privateKeyBase64']
        if not private_key.startswith('-----BEGIN'):
            raise RuntimeError('Unexpected private key format; inspect AWS key pair before proceeding.')
        descriptor = os.open(pem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write(private_key)
    with urlopen('https://checkip.amazonaws.com', timeout=15) as response:
        admin_ip = response.read().decode().strip()
    import ipaddress
    ipaddress.IPv4Address(admin_ip)
    aws('lightsail', 'create-instances', instanceNames=[NAME], availabilityZone='ap-south-1a',
        blueprintId='ubuntu_24_04', bundleId='small_3_1', keyPairName=KEY_NAME,
        userData=(ROOT / 'deploy' / 'bootstrap.sh').read_text(encoding='utf-8'),
        tags=[{'key': 'Application', 'value': 'wapp'}, {'key': 'Domain', 'value': 'wapp.neorizsolutions.com'}])
    print('Approved Lightsail instance creation requested.', flush=True)
    for _ in range(30):
        instance = aws('lightsail', 'get-instance', instanceName=NAME)['instance']
        if instance['state']['name'] == 'running':
            break
        time.sleep(10)
    else:
        raise RuntimeError('Instance still provisioning; inspect AWS before retrying.')
    aws('lightsail', 'put-instance-public-ports', instanceName=NAME, portInfos=[
        {'fromPort': 22, 'toPort': 22, 'protocol': 'tcp', 'cidrs': [admin_ip + '/32'], 'ipv6Cidrs': []},
        {'fromPort': 80, 'toPort': 80, 'protocol': 'tcp', 'cidrs': ['0.0.0.0/0'], 'ipv6Cidrs': ['::/0']},
        {'fromPort': 443, 'toPort': 443, 'protocol': 'tcp', 'cidrs': ['0.0.0.0/0'], 'ipv6Cidrs': ['::/0']},
    ])
    aws('lightsail', 'allocate-static-ip', staticIpName=NAME + '-ip')
    aws('lightsail', 'attach-static-ip', staticIpName=NAME + '-ip', instanceName=NAME)
    address = aws('lightsail', 'get-static-ip', staticIpName=NAME + '-ip')['staticIp']['ipAddress']
    (PRIVATE / 'instance.json').write_text(json.dumps({'name': NAME, 'region': REGION, 'ip': address}), encoding='utf-8')
    print(f'Server ready: {NAME}; static IPv4: {address}; SSH restricted to your current public IP.', flush=True)


if __name__ == '__main__':
    main()
