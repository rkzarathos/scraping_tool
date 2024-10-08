#!/usr/bin/env python
# coding: utf-8

# In[1]:



import os
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By

from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementNotInteractableException, StaleElementReferenceException

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait 
from tqdm import tqdm
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import langchain
from langchain.chains import retrieval
from langchain_community.chat_models import ChatOpenAI
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PDFMinerLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
import warnings

# Set environment variables
os.environ["GIT_PYTHON_REFRESH"] = "quiet"
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = 'C:/Program Files/Git'
os.environ['LANGCHAIN_TRACING_V2'] = 'true'
os.environ['LANGCHAIN_ENDPOINT'] = 'https://api.smith.langchain.com'
os.environ['LANGCHAIN_API_KEY'] = "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"
os.environ['OPENAI_API_KEY'] = "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"

# Ignore warnings
warnings.filterwarnings("ignore")


root = tk.Tk()
root.title("Scraping Tool")

def scrape_cases(courtrooms, start_date, end_date, download_directory, progress_bar):
    case_data = pd.DataFrame(columns=['case_numbers', 'case_titles', "courtroom", "Status", "Path"])

    options = Options()
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.headless = False
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=360,800')

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    progress_bar["maximum"] = len(courtrooms)

    for courtroom in tqdm(courtrooms):
        max_attempts = 5
        reload_interval = 5
        url = 'https://courtsportal.dallascounty.org/DALLASPROD/Home/Dashboard/26'

        for attempt in range(max_attempts):
            try:
                driver.get(url)
                break
            except TimeoutException:
                time.sleep(reload_interval)
        else:
            print("Page failed to load after maximum attempts")

        time.sleep(5)

        try:
            iframe = driver.find_element(By.TAG_NAME, "iframe")
            driver.switch_to.frame(iframe)
        except NoSuchElementException:
            pass

        formdata = {
            'SearchCriteria.SelectedCourt': 'All Locations',
            'SearchCriteria.Selected.HearingTypes': 'All Available Civil Hearing Types',
            'SearchCriteria.SearchByType': 'Courtroom',
            'SearchCriteria.SelectedCourtRoom': courtroom,
            'SearchCriteria.DateFrom': start_date,
            'SearchCriteria.DateTo': end_date
        }

        for key, value in formdata.items():
            try:
                element = driver.find_element(By.NAME, key)
                if key in ['SearchCriteria.SearchValue', 'SearchCriteria.DateFrom', 'SearchCriteria.DateTo']:
                    element.clear() 
                element.send_keys(value)
            except NoSuchElementException:
                pass

        try:
            submit_button = driver.find_element(By.XPATH, "//input[@type='submit']")
            submit_button.click()
        except NoSuchElementException:
            pass

        time.sleep(15) 

        page_number = 1

        while True:
            try:
                case_data = scrape_page(case_data, courtroom, driver)
                page_number += 1
                next_button_xpath = f"//a[@class='k-link' and @data-page='{page_number}']/span[@class='k-icon k-i-arrow-e']"
                next_button = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, next_button_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)  # Scroll to the button
                driver.execute_script("arguments[0].click();", next_button)  # Click the button using JavaScript
                time.sleep(20)

            except (TimeoutException, NoSuchElementException, StaleElementReferenceException):
                break
         
        progress_bar.step(1)
        root.update_idletasks()
    progress_bar["value"] = progress_bar["maximum"]
    driver.quit()
    return case_data

def scrape_page(case_data, courtroom, driver):
    case_numbers = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.XPATH, "//span[@class='card-heading show-only-in-mobile-view noprint']"))
    )

    case_titles = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.XPATH, "//*[contains(@class, 'data-subheading')]"))
    )

    cr_labels = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.XPATH, "//div[@class='data-label' and text()='Courtroom']"))
    )
    crs = []
    for cr_label in cr_labels:
        # Find the next sibling element with class 'data-value'
        value = cr_label.find_element(By.XPATH, "following-sibling::div[@class='data-value']")
        crs.append(value.text)

    if len(case_numbers) == 1 and len(case_titles) == 1 and len(crs) == 1:
        try:
            element = driver.find_element(By.CLASS_NAME, 'text-primary')
            case_number = element.text.split('|')[0].strip()
            case_title = element.text.split('|')[1].strip()
            cr = courtroom
            dyn_index = len(case_data)
            case_data.loc[dyn_index] = [case_number, case_title, cr, "", ""]
        except IndexError:
            for case_number, case_title, cr in zip(case_numbers, case_titles, crs):
                case_data = add_case_data(case_data, case_number, case_title, cr)

    else:
        for case_number, case_title, cr in zip(case_numbers, case_titles, crs):
            case_data = add_case_data(case_data, case_number, case_title, cr)

    return case_data

def add_case_data(case_data, case_number, case_title, cr):
    dyn_index = len(case_data)
    case_data.loc[dyn_index] = [case_number.text, case_title.text, cr, "", ""]
    return case_data

# Function to scrape documents based on case data
def start_document_scraping(case_data, new_download_dir, start_date, end_date, download_directory, progress_bar):
    # Create a new directory with a timestamp to ensure uniqueness
    

    options = Options()
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    #options.add_argument("--headless")
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=360,800')

    driver = webdriver.Chrome(options=options)
    progress_bar["maximum"] = len(case_data)
    for i in tqdm(range(len(case_data))):
        url = 'https://courtsportal.dallascounty.org/DALLASPROD/Home/Dashboard/26'
        driver.get(url)
        time.sleep(5)

        try:
            iframe = driver.find_element(By.TAG_NAME, "iframe")
            driver.switch_to.frame(iframe)
        except NoSuchElementException:
            pass

        formdata = {
            'SearchCriteria.SelectedCourt': 'All Locations',
            'SearchCriteria.Selected.HearingTypes': 'All Hearings',
            'SearchCriteria.SearchByType': 'Case Number',
            'SearchCriteria.SearchValue': case_data["case_numbers"][i],
            'SearchCriteria.DateFrom': start_date,
            'SearchCriteria.DateTo': end_date
        }

        for key, value in formdata.items():
            try:
                element = driver.find_element(By.NAME, key)
                if key in ['SearchCriteria.SearchValue', 'SearchCriteria.DateFrom', 'SearchCriteria.DateTo']:
                    element.clear() 
                element.send_keys(value)
            except NoSuchElementException:
                pass

        try:
            submit_button = driver.find_element(By.XPATH, "//input[@type='submit']")
            submit_button.click()
        except NoSuchElementException:
            pass

        time.sleep(5)

        try:
            view_button = driver.find_element(By.XPATH, "//button[contains(@class, 'data-label md-button noprint') and text()='View']")
            view_button.click()
        except (NoSuchElementException, ElementNotInteractableException):
            pass

        try:
            op_button = driver.find_element(By.XPATH, "//a[@class='btn btn-default document-download' and @data-doc-doctype='PETITION' and contains(translate(@data-doc-docname, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'original') and contains(translate(@data-doc-docname, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'petition')]")
            op_button.click()
            time.sleep(30)

            # Check for downloaded PDF files
            pdf_files = [file for file in os.listdir(download_directory) if file.endswith('.pdf')]
            if pdf_files:
                pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(download_directory, x)), reverse=True)
                most_recent_pdf = pdf_files[0]  # Get the most recent PDF file

                original_path = os.path.join(download_directory, most_recent_pdf)
                new_name = f"{case_data['case_numbers'][i]}.pdf"
                new_path = os.path.join(new_download_dir, new_name)

                os.rename(original_path, new_path)
            case_data.loc[i, "Status"] = "Original Petition obtained"
            case_data.loc[i, "Path"] = new_path
        except NoSuchElementException:
            case_data.loc[i, "Status"] = "Original Petition button not found"
        except FileExistsError:
            case_data.loc[i, "Status"] = "Original Petition already exists"

        progress_bar.step(1)
        root.update_idletasks()
    progress_bar["value"] = progress_bar["maximum"]
    driver.quit()

# Function to process case data for receivership analysis
def process_receivership_analysis(case_data, new_download_dir, progress_bar):
    final_df = case_data[case_data["Status"] == "Original Petition obtained"]

    questions = [
        "What is the case summary?",
        "Who is the plaintiff?",
        "Who is the defendant?",
        "What is the case number?",
        "What is the courtroom to which this case is assigned?",
        "What is the case filing date?",
        "Who are the lawyers or law firms involved on either side?",
        "Who is the judge assigned to the case?",
        "What is the property or asset in dispute?",
        "What is the value of the property or asset in question?",
        "What is the value of the claim in the case?",
        "Is there a possibility of a receivership occurring in this case?",
        "What is the Receivership Likelihood score?",
        "Keywords Identified to indicate potential receivership?"
    ]

    new_columns = final_df.columns.tolist() + questions
    final_df = final_df.reindex(columns=new_columns)
    final_df.reset_index(inplace=True)
    llm = ChatOpenAI(model_name="gpt-4-turbo", temperature=0.2)

    prompt = ChatPromptTemplate.from_template(""" 
                You are a Receivership Assistant. Your role is to help the legal department assess whether there is a possibility for a receivership based on the provided case petition document. You must answer each question directly, providing only the required answer with no additional explanation or introductory phrases.

                Receivership Likelihood Scoring System (for evaluating case petition documents):
                0 - No Chance of a Receivership: Unrelated to financial or business issues.
                1 - Very Low Likelihood: No significant indicators of mismanagement, insolvency, or risk to assets. No request for a receiver.
                2 - Low Likelihood: Some mention of financial distress and property/asset due to business issues but no clear request for a receiver or strong indication of mismanagement.
                3 - Moderate Likelihood: Evidence of financial distress, mismanagement, property/asset and conflict, but the need for a receiver is not explicitly mentioned or strongly argued.
                4 - High Likelihood: Strong indications of insolvency, asset mismanagement, and internal conflicts. Clear request or strong basis for appointing a receiver.
                5 - Very High Likelihood: The petition directly asks for a receiver, highlights urgent asset risk, and contains overwhelming evidence of insolvency or mismanagement.
                
                Here is the original petition document:
                
                {context}
                
                Answering Guidelines:
                Case Summary: Provide a concise summary of the case in no more than 4-5 sentences. Include the most pertinent information.
                Case Numbers: Provide only the case number, e.g., DC-21-0830.
                Dates: Provide only the date, e.g., February 10, 2021.
                Names of Parties (Plaintiff/Defendant): Provide only the name, e.g., CREDIT HUMAN FEDERAL CREDIT UNION.
                Scores: Provide only the numeric score, e.g., 3.
                Yes/No Questions (e.g., Is there a possibility of a receivership?): Strictly respond with "Yes" if the likelihood score is above 1, otherwise respond with "No."
                Property Information: Provide the property name followed by the address or value, based on the question.
                Missing Information: If the relevant information is not available, respond with "Information unavailable."
                
                Expected Format for Questions:
                What is the case number?
                DC-21-0830
                
                What is the case filing date?
                February 10, 2021
                
                What is the Receivership Likelihood score?
                3
                
                Who is the plaintiff?
                CREDIT HUMAN FEDERAL CREDIT UNION
                
                Who is the defendant?
                John Doe
                
                Is there a possibility of a receivership occurring in this case?
                Yes
                
                What is the property or asset in dispute?
                Evergreen Apartments
                
                Now answer the following question strictly using the information and format given above:
                
                Question:
                {input}
                
                Provide a consistent, concise, and accurate response based on the case petition document.
                    """)

    def doc_parser_qa(i):
        data = (PDFMinerLoader(final_df["Path"][i])).load()
        document_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=1200, chunk_overlap=300, separators=[" ", ",", "\n"])
        docs = document_splitter.split_documents(data)
        embeddings = OpenAIEmbeddings()
        vectorstore = Chroma.from_documents(documents=docs, embedding=embeddings)

        document_chain = create_stuff_documents_chain(llm, prompt)
        retriever = vectorstore.as_retriever(search_kwargs={"k": min(len(docs), 4)})
        retrieval_chain = create_retrieval_chain(retriever, document_chain)

        for question in questions:
            final_df.loc[i, question] = retrieval_chain.invoke({"input": question})["answer"]

        vectorstore.delete_collection()
        return True

    for i in tqdm(range(len(final_df))):
        start_time = time.time()
        results = doc_parser_qa(i)
        while time.time() - start_time < 300:
            if results:
                break
            time.sleep(1)
        else:
            continue
        progress_bar.step(1)
        time.sleep(10)
        root.update_idletasks()

    progress_bar["value"] = progress_bar["maximum"]
    final_df.to_csv(f'{new_download_dir}/scrape_results.csv', index=False)

# Function to open the GUI for user input
def open_gui():


    # Set a fixed size for the window
    root.geometry("800x600")

    # Configure layout and centering
    for i in range(4):
        root.grid_rowconfigure(i, weight=1)
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    root.grid_columnconfigure(2, weight=1)

    # Title Label
    title_label = tk.Label(root, text="Scraping Tool", font=("Arial", 20))
    title_label.grid(row=0, column=0, columnspan=3, pady=20)

    # Entry Widgets
    tk.Label(root, text="Start Date (MM/DD/YYYY):").grid(row=1, column=0, padx=10, pady=10)
    start_date_entry = tk.Entry(root)
    start_date_entry.grid(row=1, column=1, padx=10, pady=10)

    tk.Label(root, text="End Date (MM/DD/YYYY):").grid(row=2, column=0, padx=10, pady=10)
    end_date_entry = tk.Entry(root)
    end_date_entry.grid(row=2, column=1, padx=10, pady=10)

    tk.Label(root, text="Download Directory:").grid(row=3, column=0, padx=10, pady=10)
    directory_entry = tk.Entry(root, width=50)
    directory_entry.grid(row=3, column=1, padx=10, pady=10)

    def browse_directory():
        directory = filedialog.askdirectory()
        if directory:
            directory_entry.delete(0, tk.END)
            directory_entry.insert(0, directory)

    tk.Button(root, text="Browse", command=browse_directory).grid(row=3, column=2, padx=10, pady=10)

    # Create Progress Bars
    tk.Label(root, text="Scraping Cases Progress:").grid(row=4, column=0, padx=10, pady=10)
    scraping_progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
    scraping_progress.grid(row=4, column=1, columnspan=2, pady=10)

    tk.Label(root, text="Downloading Documents Progress:").grid(row=5, column=0, padx=10, pady=10)
    download_progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
    download_progress.grid(row=5, column=1, columnspan=2, pady=10)

    tk.Label(root, text="Receivership Analysis Progress:").grid(row=6, column=0, padx=10, pady=10)
    analysis_progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
    analysis_progress.grid(row=6, column=1, columnspan=2, pady=10)

    def on_submit():
        start_date = start_date_entry.get()
        end_date = end_date_entry.get()
        download_directory = directory_entry.get()
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        new_download_dir = os.path.join(download_directory, f"Dallas_County_Scrape_run_{timestamp}")
        os.makedirs(new_download_dir, exist_ok=True)

        

        if start_date and end_date and download_directory:
            courtroom_list = [
                                "14TH DISTRICT COURT",
                                "44TH DISTRICT COURT",
                                "68TH DISTRICT COURT",
                                "95TH DISTRICT COURT",
                                "101ST DISTRICT COURT",
                                "116TH DISTRICT COURT",
                                "134TH DISTRICT COURT",
                                "160TH DISTRICT COURT",
                                "162ND DISTRICT COURT",
                                "191ST DISTRICT COURT",
                                "192ND DISTRICT COURT",
                                "193RD DISTRICT COURT",
                                "298TH DISTRICT COURT",
                                "254TH DISTRICT COURT",
                                "255TH DISTRICT COURT",
                                "256TH DISTRICT COURT",
                                "301ST DISTRICT COURT",
                                "302ND DISTRICT COURT",
                                "303RD DISTRICT COURT",
                                "330TH DISTRICT COURT"
                                ]

            # Start scraping, downloading, and processing while updating progress bars
            case_data = scrape_cases(courtroom_list, start_date, end_date, download_directory, scraping_progress)
            start_document_scraping(case_data, new_download_dir, start_date, end_date, download_directory, download_progress)
            # Implement the receivership analysis functionality here, updating the analysis_progress bar
            process_receivership_analysis(case_data, new_download_dir, analysis_progress)

            root.destroy()  # Close the GUI when complete
        else:
            messagebox.showwarning("Input Error", "Please fill in all fields.")

    tk.Button(root, text="Submit", command=on_submit).grid(row=7, columnspan=3, pady=20)

    root.mainloop()

# Run the GUI
open_gui()


# In[ ]:




