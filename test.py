import requests
from PyPDF2 import PdfReader
from docx import Document
from partd.file import filename
from striprtf.striprtf import rtf_to_text

#print(requests.certs.where())

url = 'https://dokb-orel.com/wp-content/uploads/2022/05/perechen-lekarstvennyh-preparatov-prednaznachennyh-dlya-obespecheniya-licz-bolnyh-gemofiliej-mukovisczidozom....docx'
r = requests.get(url, verify=False)
print(r.url)
print(r.headers)
print(r.url)
print(r.status_code)

filename = "test.result.docx"
with open(filename, 'wb') as file:
    file.write(r.content)

doc = Document(filename)
text =  ' '.join([p.text for p in doc.paragraphs])
print(text)