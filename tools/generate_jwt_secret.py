#!/usr/bin/env python3
import os
import base64

def main():
    # 48 random bytes -> 64-char base64 string (approx)
    raw = os.urandom(48)
    b64 = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    print(b64)

if __name__ == "__main__":
    main()

