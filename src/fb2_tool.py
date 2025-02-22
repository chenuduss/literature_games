import docx
import sys
from datetime import datetime

from litgb_exception import UnknownFileFormatException
 
def GetParagraphs(doc:docx.Document) -> list[str]:
    result = []
    for para in doc.paragraphs:	
        result.append(para.text)
    
    return result

def NormalizeParagraph(par:str) -> str:
    return par.strip(" \t")

def MakeParagraph(par:str)->str:
    return "<p>"+NormalizeParagraph(par)+"</p>"

def GetTextSize(par:str) -> int:
    return len(par)

def MakeSection(pars:list[str], title:str)-> tuple[str, int]:
    result = "<section>\n<title><p>"+title+"</p></title>\n"
    text_size = 0
    for p in pars:
        text_size += GetTextSize(p)
        result += MakeParagraph(p)
        result += "\n"

    result += "</section>"

    return (result, text_size)


def SectionToFb2(section_filename:str, dest_filename:str, title:str):

    with open(section_filename, 'r') as content_file:
        f2b_section_content = content_file.read()

    date_value_short = datetime.now().strftime("%Y-%m-%d")
    date_value_long = datetime.now().strftime("%Y-%m-%d %H:%M")

    result = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<FictionBook xmlns:l=\"http://www.w3.org/1999/xlink\" xmlns=\"http://www.gribuser.ru/xml/fictionbook/2.0\">"
    result += "<description>\n<title-info> <genre>litg_bot</genre> <author> <first-name>anonymous</first-name> <last-name>anonymous</last-name> <home-page>https://author.today/</home-page></author>"
    result += "<book-title>"+title+"</book-title> <annotation><p>no annotaion</p> </annotation>"
    result += "<date value=\""+date_value_short+"\">"+date_value_long+"</date><lang>ru</lang></title-info>"
    result += "\n<document-info><author> <first-name>anonymous</first-name><last-name>anonymous</last-name> <home-page>https://author.today/</home-page></author>"
    result += "<date value=\""+date_value_short+"\">"+date_value_long+"</date><id>33247</id><version>1.00</version>\n</document-info>\n<publish-info />\n</description>"
    result += "\n<body>\n<title>"+title+"</title>\n"
    
    result += f2b_section_content

    result += "\n</body>"

    with open(dest_filename, 'w') as f:
        f.write(result)

def SaveSection(dest_filename:str, text:str):
    with open(dest_filename, 'w') as f:
        f.write(text)

def TxtToFb2Section(source_filename:str, dest_filename:str, title:str)  -> int:
    ps = []
    with open(source_filename, "r") as file:
        for line in file:
            ps.append(line)
    
    section_text, text_size = MakeSection(ps, title)
    SaveSection(dest_filename, section_text)
    return  text_size  

def DocToFb2Section(source_filename:str, dest_filename:str, title:str)  -> int:
    doc = docx.Document(source_filename)    
    ps = GetParagraphs(doc)
    section_text, text_size = MakeSection(ps, title)
    SaveSection(dest_filename, section_text)
    return  text_size

def FileToFb2Section(source_filename:str, dest_filename:str, title:str) -> int:
    if source_filename.endswith("docx"):
        return DocToFb2Section(source_filename, dest_filename, title)
    elif source_filename.endswith("txt"):
        return TxtToFb2Section(source_filename, dest_filename, title)    
    
    raise UnknownFileFormatException(None)


def main():
    DocToFb2(sys.argv[1], sys.argv[2], sys.argv[1])
    

if __name__ == '__main__':    
    main()
