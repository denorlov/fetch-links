import os
import shutil
import zipfile

import requests
from ssl import SSLError
import urllib3

urllib3.disable_warnings()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import patoolib
from PyPDF2 import PdfReader
from docx import Document
from striprtf.striprtf import rtf_to_text
from bs4 import BeautifulSoup
import pandas as pd
from humanize import naturalsize
import re

FILE_EXT = {'.pdf', '.doc', '.docx', '.rtf', '.csv', '.xls', '.xlsx'}
ANCHOR_TEXT = {'договор', 'оферт', 'услов', 'политика', 'конфиденц', 'реквизиты', 'соглаш', 'пользов', 'персональн', 'юридич', 'право', 'информ'}

def extract_text_from_pdf(pdf_filepath):
    with open(pdf_filepath, 'rb') as file:
        reader = PdfReader(file)
        return ' '.join([page.extract_text() for page in reader.pages])

def extract_text_from_docx(docx_file):
    doc = Document(docx_file)
    return ' '.join([p.text for p in doc.paragraphs])

def extract_text_from_rtf(rtf_file):
    with open(rtf_file) as file:
        content = file.read().decode('utf-8')
        text = rtf_to_text(content)
        return text

def extract_text_from_csv(csv_filepath):
    df = pd.read_csv(csv_filepath)
    return df.to_string()

def extract_text_from_excel(excel_filepath):
    df = pd.read_excel(excel_filepath)
    return df.to_string()

def download_and_extract_text(url, target_directory, output_filename, delete_intermidiate_file=False):
    filename = os.path.join(target_directory, output_filename)
    print(f"downloading {url} to {filename}")
    try:
        response = requests.get(url, verify=False)
        file_len = response.headers.get('Content-Length', 0)
        print(f"Response: {response}, {naturalsize(file_len)}")

        if response.status_code == 200 and (int(file_len) <= 3 * 1024 * 1024):
            print(f"writing {url} to {filename}")
            with open(filename, 'wb') as file:
                file.write(response.content)

            text = None
            if filename.endswith('.pdf'):
                text = extract_text_from_pdf(filename)
            elif filename.endswith('.doc') or filename.endswith('.docx'):
                text = extract_text_from_docx(filename)
            elif filename.endswith('.rtf'):
                text = extract_text_from_rtf(filename)
            elif filename.endswith('.csv'):
                text = extract_text_from_csv(filename)
            elif filename.endswith('.xls') or filename.endswith('.xlsx'):
                text = extract_text_from_excel(filename)

            if delete_intermidiate_file:
                #print(f"removing {filename}")
                os.remove(filename)

            if text:
                txt_filename = filename[:-4] + '.txt'
                print(f"writing text of {url} to {txt_filename}")
                with open(txt_filename, 'w', encoding='utf-8') as txt_file:
                    txt_file.write(text)
    except (Exception, SSLError) as e:
        print(e)

RU_CONTENTS_PATTERN = re.compile(r"[\u0400-\u04FF]")

def process_html_file(original_arch_filepath, zip_arch_file: zipfile.ZipFile, inner_html_filename):
    with zip_arch_file.open(inner_html_filename) as html_file:
        html_content = html_file.read()

        #print(f"processing {original_arch_filepath}, {inner_html_filename}, contents: {html_content[:50]}")

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            if not RU_CONTENTS_PATTERN.search(str(soup)):
                print(f"{inner_html_filename} doesnt contain russian text, will skip it")
                return []

            links = soup.find_all('a', href=True)
            resulting_links = []

            for link in links:
                for ex in FILE_EXT:
                    if link['href'].endswith(ex):
                        resulting_links.append(link)

            links = []
            if len(resulting_links) > 10:
                #print(f"too much links: {resulting_links}")
                for link in resulting_links:
                    for anch_text in ANCHOR_TEXT:
                        if anch_text in str(link):
                            links.append(link)
                print(f"links filtered by keywords: {links}")

            return links
        except Exception as e:
            print(e)
            return []


def process_zip(zip_filepath, processed_site_archs_file, processed_site_arcs: set):
    if zip_filepath in processed_site_arcs:
        print(f"skip processing of {zip_filepath}, it already was processed")
        return

    print(f"processing zip file: {zip_filepath}")
    with zipfile.ZipFile(zip_filepath, mode="a") as zip_arch_file:
        zip_arch_file.testzip()

        links = []
        for file_info in zip_arch_file.infolist():
            inner_filename = file_info.filename
            if inner_filename.endswith(".html"):
                links = links + process_html_file(zip_filepath, zip_arch_file, inner_filename)

        for link in set(links[:10]):
            href = link['href']
            target_directory = os.path.split(zip_arch_file.filename)[0]
            target_filename = os.path.basename(href)

            if href.startswith('https://drive.google.com'):
                print(f"google drive link: {href}")
                # file_id = re.search(r'/file/d/([a-zA-Z0-9-_]+)/', href)
                # if file_id:
                #     gdd.download_file_from_google_drive(file_id.group(1), os.path.basename(href))
                #     download_and_extract_text(os.path.basename(href), os.path.basename(href))
            elif href.startswith("http"):
                download_and_extract_text(href, target_directory, target_filename, delete_intermidiate_file=True)
            else:
                abs_href = os.path.split(target_directory)[1] + href
                #download_and_extract_text("http://" + abs_href, target_directory, "http_" + target_filename, delete_intermidiate_file=True)
                #download_and_extract_text("https://" + abs_href, target_directory, "https_" + target_filename, delete_intermidiate_file=True)


        for dir_path, dir_name, filenames in os.walk(os.path.dirname(zip_filepath)):
            for file_name in filenames:
                #print(f"postprocessing {dir_path}, {file_name}")
                if file_name.endswith("txt"):
                    file_path = os.path.join(dir_path, file_name)
                    print(f"storing {file_path} back to {zip_arch_file}")
                    zip_arch_file.write(file_path, file_name)
                    os.remove(file_path)

    processed_site_archs_file.write(zip_filepath + "\n")
    processed_site_archs_file.flush()
                

def process_rar(
        filepath,
        processed_site_archs_file, processed_site_arcs: set
):
    print(f"processing rar file: {filepath}")
    tmp_dir = "./tmp"

    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)

    os.mkdir(tmp_dir)
    patoolib.extract_archive(filepath, outdir=tmp_dir)

    for root, _, files in os.walk(tmp_dir):
        for file in files:
            if file.endswith('.zip'):
                arch_filepath = os.path.join(root, file)
                process_zip(arch_filepath, processed_site_archs_file, processed_site_arcs)

    #shutil.rmtree(tmp_dir)

def process_directory(
        directory,
        processed_archs_file, processed_arcs:set,
        processed_site_archs_file, processed_site_arcs:set
):
    for root, _, files in os.walk(directory):
        for file in files:
            arch_filepath = os.path.join(root, file)

            if file.endswith('.rar'):
                arch_filepath = os.path.join(root, file)
                if arch_filepath in processed_arcs:
                    print(f"skip processing of {arch_filepath}, it already was processed")
                    continue

                process_rar(arch_filepath, processed_site_archs_file, processed_site_arcs)
                processed_archs_file.write(arch_filepath + "\n")
                processed_archs_file.flush()
            elif file.endswith('.zip'):
                process_zip(arch_filepath, processed_site_archs_file, processed_site_arcs)

base_directory = "./data/results"
processed_archives_file_path = "./processed_archives.txt"
processed_site_archives_file_path = "./processed_site_archives.txt"

processed_arcs = set()
processed_site_arcs = set()

if os.path.exists(processed_archives_file_path):
    with open(processed_archives_file_path) as processed_arcs_file:
        processed_arcs = set(processed_arcs_file.read().splitlines())
        # print(f"processed_arcs: {processed_arcs}")

if os.path.exists(processed_site_archives_file_path):
    with open(processed_site_archives_file_path) as processed_site_arcs_file:
        processed_site_arcs = set(processed_site_arcs_file.read().splitlines())
        # print(f"processed_site_arcs: {processed_site_arcs}")


with open(processed_archives_file_path, "a", encoding="utf-8") as processed_arcs_file:
    with open(processed_site_archives_file_path, "a", encoding="utf-8") as processed_site_arcs_file:
        process_directory(
            base_directory,
            processed_arcs_file, processed_arcs,
            processed_site_arcs_file, processed_site_arcs
        )

# todo
# * if site links more than 10, filter by keywords - done
# * collect all links from all pages of the site, to make file download only once - done
# * process links without base url (/abc/efg.rtf) - done
# * prepare requirements.txt - done
# * save last succesfully processed archive, restart processing from that point - done
# * rar resulting archive
# * support google drive
# * support y disk
