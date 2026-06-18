"""
Gerador de PDF para Faturas/Recibos
Usa reportlab para criar documentos profissionais
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import os


def generate_repair_pdf(repair: dict, output_path: str) -> bool:
    """
    Gera um PDF profissional para uma reparação
    
    Args:
        repair: Dicionário com dados da reparação:
            - id: ID da reparação
            - client: Nome do cliente
            - description: Descrição da reparação
            - used_parts: String com componentes utilizados
            - total: Custo total
            - date: Data da reparação
            - payment_status: Estado do pagamento
    
    Returns:
        True se sucesso, False se erro
    """
    try:
        # Criar documento PDF
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Container para elementos
        story = []
        
        # Estilos
        styles = getSampleStyleSheet()
        
        # Estilo personalizado para título
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#FF5722'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Estilo para subtítulos
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        
        # Estilo para texto normal
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#333333'),
            spaceAfter=10
        )
        
        # Estilo para total
        total_style = ParagraphStyle(
            'CustomTotal',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#FF5722'),
            spaceAfter=20,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        )
        
        # Estilo para disclaimer
        disclaimer_style = ParagraphStyle(
            'CustomDisclaimer',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#666666'),
            alignment=TA_CENTER,
            spaceBefore=30
        )
        
        # HEADER: Nome da empresa
        title = Paragraph("INDUTECHPRO", title_style)
        story.append(title)
        
        # Data
        date_str = repair.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            formatted_date = dt.strftime("%d/%m/%Y %H:%M")
        except:
            formatted_date = date_str
        
        date_para = Paragraph(f"Data: {formatted_date}", normal_style)
        story.append(date_para)
        story.append(Spacer(1, 0.5*cm))
        
        # SECÇÃO 1: Cliente e Descrição
        story.append(Paragraph("Dados da Reparação", subtitle_style))
        
        # Tabela de informações do cliente
        client_data = [
            ["Cliente:", repair.get("client", "N/A")],
            ["Descrição:", repair.get("description", "N/A")],
            ["Nº Reparação:", f"#{repair.get('id', 'N/A')}"]
        ]
        
        client_table = Table(client_data, colWidths=[4*cm, 12*cm])
        client_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0'))
        ]))
        
        story.append(client_table)
        story.append(Spacer(1, 0.5*cm))
        
        # SECÇÃO 2: Componentes Utilizados
        story.append(Paragraph("Componentes Utilizados", subtitle_style))
        
        used_parts_str = repair.get("used_parts", "")
        if used_parts_str and used_parts_str.strip() and used_parts_str != "Nenhum":
            # Parse componentes (formato: "CODE (Qtyx), CODE2 (Qtyx)" ou string simples)
            parts_list = []
            
            # Tentar parsear componentes
            try:
                # Se for formato estruturado com vírgulas
                if "," in used_parts_str:
                    parts = used_parts_str.split(",")
                    for part in parts:
                        part = part.strip()
                        if "(" in part and ")" in part:
                            # Formato: "CODE (Qtyx)" ou "CODE (Qty)"
                            name = part.split("(")[0].strip()
                            qty_str = part.split("(")[1].split(")")[0].strip()
                            # Remover 'x' se existir (ex: "2x" -> "2")
                            qty_str = qty_str.replace("x", "").strip()
                            parts_list.append({"name": name, "qty": qty_str, "price": "N/A"})
                        else:
                            parts_list.append({"name": part, "qty": "1", "price": "N/A"})
                else:
                    # String simples ou formato único
                    if "(" in used_parts_str and ")" in used_parts_str:
                        name = used_parts_str.split("(")[0].strip()
                        qty_str = used_parts_str.split("(")[1].split(")")[0].strip()
                        qty_str = qty_str.replace("x", "").strip()
                        parts_list.append({"name": name, "qty": qty_str, "price": "N/A"})
                    else:
                        parts_list.append({"name": used_parts_str, "qty": "1", "price": "N/A"})
            except:
                # Se falhar, usar string completa
                parts_list.append({"name": used_parts_str, "qty": "1", "price": "N/A"})
            
            # Criar tabela de componentes
            if parts_list:
                parts_table_data = [["Componente", "Quantidade", "Preço"]]
                for part in parts_list:
                    parts_table_data.append([
                        part.get("name", "N/A"),
                        part.get("qty", "1"),
                        part.get("price", "N/A")
                    ])
                
                parts_table = Table(parts_table_data, colWidths=[10*cm, 3*cm, 3*cm])
                parts_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FF5722')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                    ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e0e0e0')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
                ]))
                
                story.append(parts_table)
            else:
                story.append(Paragraph("Nenhum componente registado", normal_style))
        else:
            story.append(Paragraph("Nenhum componente registado", normal_style))
        
        story.append(Spacer(1, 1*cm))
        
        # FOOTER: Total
        total = repair.get("total", 0.0)
        total_para = Paragraph(f"Total: {total:.2f} €", total_style)
        story.append(total_para)
        
        # Estado de pagamento
        payment_status = repair.get("payment_status", "Pendente")
        status_color = colors.HexColor('#4CAF50') if payment_status == "Pago" else colors.HexColor('#FF9800')
        status_style = ParagraphStyle(
            'PaymentStatus',
            parent=styles['Normal'],
            fontSize=12,
            textColor=status_color,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        )
        status_para = Paragraph(f"Estado: {payment_status}", status_style)
        story.append(status_para)
        
        story.append(Spacer(1, 1*cm))
        
        # Disclaimer legal
        disclaimer = Paragraph(
            "Garantia de 3 meses. Obrigado pela preferência.",
            disclaimer_style
        )
        story.append(disclaimer)
        
        # Construir PDF
        doc.build(story)
        return True
    
    except Exception as e:
        print(f"Erro ao gerar PDF: {str(e)}")
        return False
