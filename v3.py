with open(r'D:\AI\alphapilot\部署文件\frontend\app\cn\page.tsx', 'rb') as f:
    raw = f.read()
print('Has sniper-card:', b'sniper-card' in raw)
print('Has simplified name:', b'text-[13px] font-medium text-[#EAF2FF]' in raw)
print('Has old name size:', b'text-[14px] font-medium text-[#EAF2FF]' in raw)
print('Has old sniper classes:', b'rounded-lg bg-[#121c2a] p-2.5 hover' in raw)
