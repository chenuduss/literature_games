import docx
import sys

from litgb_exception import UnknownFileFormatException
 
def GetParagraphs(doc:docx.Document) -> list[str]:
    result = []
    for para in doc.paragraphs:	
        result.append(para.text)
    
    return result

def NormalizeParagraph(par:str)->str:
    return par

def MakeParagraph(par:str)->str:
    return "<p>"+NormalizeParagraph(par)+"</p>"

def MakeSection(pars:list[str], title:str)->str:
    result = "<section>\n<title><p>"+title+"</p></title>\n"
    for p in pars:
        result += MakeParagraph(p)
        result += "\n"

    result += "</section>"

    return result


def MakeFB2(pars:list[str], title:str) -> str:
    date_value_short = "2019-11-07"
    date_value_long = "2019-11-07 12:00:00"

    result = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<FictionBook xmlns:l=\"http://www.w3.org/1999/xlink\" xmlns=\"http://www.gribuser.ru/xml/fictionbook/2.0\">"
    result += "<description>\n<title-info> <genre>ysdb_bot</genre> <author> <first-name>anonymous</first-name> <last-name>anonymous</last-name> <home-page>https://author.today/</home-page></author>"
    result += "<book-title>"+title+"</book-title> <annotation><p>no annotaion</p> </annotation>"
    result += "<date value=\""+date_value_short+"\">"+date_value_long+"</date><lang>ru</lang></title-info>"
    result += "\n<document-info><author> <first-name>anonymous</first-name><last-name>anonymous</last-name> <home-page>https://author.today/</home-page></author>"
    result += "<date value=\""+date_value_short+"\">"+date_value_long+"</date><id>33247</id><version>1.00</version>\n</document-info>\n<publish-info />\n</description>"
    result += "\n<body>\n<title>"+title+"</title>\n"
    
    result += MakeSection(pars, title)

    result += "\n</body>"

    return result

def DocToFb2(source_filename:str, dest_filename:str, title:str):
    doc = docx.Document(source_filename)    
    ps = GetParagraphs(doc)
    with open(dest_filename, 'w') as f:
        f.write(MakeFB2(ps, title))

def FileToFb2(source_filename:str, dest_filename:str, title:str):
    if source_filename.endswith("docx"):
        return DocToFb2(source_filename, dest_filename, title)
    
    raise UnknownFileFormatException()

def GetDocTextSize(source_filename:str) -> int:
    doc = docx.Document(source_filename)
    result = 0
    ps = GetParagraphs(doc)
    for p in ps:
        result += len(NormalizeParagraph(p))

    return result

def GetTextSize(filepath:str) -> int:
    if filepath.endswith("docx"):
        return GetDocTextSize(filepath)
    
    raise UnknownFileFormatException()
	
def main():
    DocToFb2(sys.argv[1], sys.argv[2], sys.argv[1])
    

if __name__ == '__main__':    
    main()
