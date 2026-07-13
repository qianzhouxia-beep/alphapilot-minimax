with open(r'D:\AI\alphapilot\部署文件\frontend\components\HeaderBar.tsx', 'rb') as f:
    raw = f.read()
print('Has polygon bytes:', b'polygon points' in raw)
print('Has old emoji bytes:', b'\x2b50' in raw)
print('Has /50 border:', b'/50' in raw)
