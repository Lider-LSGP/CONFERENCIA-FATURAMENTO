import hashlib,hmac,os

def hash_password(password,salt=None):
    salt=salt or os.urandom(16).hex()
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000).hex()
    return f'pbkdf2_sha256$310000${salt}${digest}'

def verify_password(password,stored):
    try:
        algo,iterations,salt,digest=stored.split('$')
        if algo!='pbkdf2_sha256' or not 100000<=int(iterations)<=1000000:return False
        got=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
        return hmac.compare_digest(got,digest)
    except (ValueError,TypeError):return False

if __name__=='__main__':
    import getpass
    print(hash_password(getpass.getpass('Senha para gerar hash: ')))
