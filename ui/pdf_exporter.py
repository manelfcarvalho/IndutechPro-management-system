"""
Exportador de PDF para Faturas/Recibos
Gera documentos profissionais usando reportlab
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from datetime import datetime
import os
from ui.utils import resource_path


def _calculate_items_table_widths(parts_list: list, available_width_pt: float) -> list:
    """Calculate item table widths, expanding the code column for the longest code."""
    qty_width = 34.0
    unit_price_width = 70.0
    total_width = 70.0
    min_code_width = 60.0
    min_description_width = 145.0

    max_code_width = max(
        min_code_width,
        available_width_pt - min_description_width - qty_width - unit_price_width - total_width,
    )

    code_values = ["Codigo"]
    code_values.extend(str(part.get("code", "")) for part in parts_list)

    code_width = min_code_width
    for code in code_values:
        font_name = "Helvetica-Bold" if code == "Codigo" else "Helvetica"
        font_size = 10 if code == "Codigo" else 9
        measured_width = pdfmetrics.stringWidth(code, font_name, font_size) + 18.0
        code_width = max(code_width, measured_width)

    code_width = min(code_width, max_code_width)
    description_width = available_width_pt - code_width - qty_width - unit_price_width - total_width

    return [code_width, description_width, qty_width, unit_price_width, total_width]


def format_currency(value: float) -> str:
    """
    Formata um valor como moeda
    
    Args:
        value: Valor numérico
    
    Returns:
        String formatada: "X.XX €"
    """
    try:
        return f"{float(value):.2f} €"
    except (ValueError, TypeError):
        return "0.00 €"


def generate_repair_pdf(repair_data: dict, filename: str, db_manager=None) -> bool:
    """
    Gera um PDF profissional para uma reparação
    
    Args:
        repair_data: Dicionário com dados da reparação
        filename: Caminho do ficheiro PDF
        db_manager: Instância do DatabaseManager (opcional, para buscar preços de componentes)
    
    Returns:
        True se sucesso, False se erro
    """
    try:
        # ========== PAGE SETUP ==========
        # Page constants (in points)
        A4_WIDTH_PT = 595.0  # A4 width in points
        MARGIN_LR_PT = 40.0  # Left/Right margins in points
        AVAILABLE_WIDTH_PT = A4_WIDTH_PT - (2 * MARGIN_LR_PT)  # ~515 points
        
        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=MARGIN_LR_PT,
            leftMargin=MARGIN_LR_PT,
            topMargin=1*inch,
            bottomMargin=1*inch
        )
        
        # Container para elementos
        story = []
        
        # Estilos
        styles = getSampleStyleSheet()
        
        # Cores
        primary_color = colors.HexColor('#2C3E50')  # Corporate Blue
        subtitle_color = colors.HexColor('#7F8C8D')  # Gray
        line_color = colors.HexColor('#BDC3C7')  # Light Gray
        light_bg = colors.HexColor('#F8F9F9')  # Very Light Gray
        secondary_color = colors.HexColor('#27AE60')  # Green (for Total)
        
        # ========== DEFINE PARAGRAPH STYLES ==========
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Normal'],
            fontSize=20,
            leading=30,  # Line height: 1.5x fontSize to prevent overlap
            textColor=primary_color,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold',
            spaceAfter=15  # Vertical spacing to create gap below title
        )
        
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=subtitle_color,
            alignment=TA_RIGHT,
            fontName='Helvetica',
            spaceAfter=1
        )
        
        section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Normal'],
            fontSize=10,
            textColor=primary_color,
            fontName='Helvetica-Bold',
            spaceAfter=6,
            textTransform='uppercase'
        )
        
        normal_text_style = ParagraphStyle(
            'NormalText',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            fontName='Helvetica',
            textColor=colors.HexColor('#2C3E50')
        )
        
        table_text_style = ParagraphStyle(
            'TableText',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#2C3E50')
        )
        
        # Define explicit alignment styles for table cells
        style_center = ParagraphStyle(
            'CenterAlign',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#2C3E50'),
            alignment=TA_CENTER  # 1=Center
        )
        
        style_right = ParagraphStyle(
            'RightAlign',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#2C3E50'),
            alignment=TA_RIGHT  # 2=Right
        )
        
        # Special Right Align style for Totals Table values (normal rows)
        style_totals_right = ParagraphStyle(
            'TotalsRightAlign',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            textColor=colors.HexColor('#2C3E50'),
            alignment=TA_RIGHT  # Right-aligned for monetary values
        )
        
        # Special Right Align style for the GRAND TOTAL (Green Bar)
        # Must be White, Bold, and Right Aligned
        style_total_final = ParagraphStyle(
            'TotalFinal',
            parent=styles['Heading4'],
            alignment=TA_RIGHT,  # Right-aligned
            textColor=colors.white,
            fontName='Helvetica-Bold',
            fontSize=12
        )
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#95A5A6'),
            alignment=TA_CENTER,
            fontName='Helvetica',
            spaceBefore=20
        )
        
        # ========== SECTION 1: HEADER ==========
        logo_path = resource_path("assets/logo.png")
        
        logo_cell = ""
        if os.path.exists(logo_path):
            try:
                # Use ImageReader to get original dimensions without modifying the file
                img_reader = ImageReader(logo_path)
                iw, ih = img_reader.getSize()
                
                # Target display width on paper (high-DPI: source pixels will be used)
                target_width = 2.5 * inch
                
                # Calculate aspect ratio from original dimensions
                aspect = ih / float(iw)
                
                # Calculate display height based on aspect ratio
                target_height = target_width * aspect
                
                # Create Image Flowable using original file path directly
                # ReportLab will use the high-res source pixels and scale them to display size
                logo_img = Image(logo_path, width=target_width, height=target_height)
                logo_img.hAlign = 'LEFT'  # Left-align the logo
                
                logo_cell = logo_img
            except Exception as e:
                print(f"Erro ao carregar logo: {e}")
                logo_cell = Paragraph("<b>INDUTECHPRO</b>", title_style)
        else:
            logo_cell = Paragraph("<b>INDUTECHPRO</b>", title_style)
        
        # Invoice Info (Right)
        repair_id = repair_data.get("id", "N/A")
        date_str = repair_data.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            formatted_date = dt.strftime("%d/%m/%Y")
        except:
            formatted_date = date_str
        
        invoice_info = [
            Paragraph("FOLHA DE OBRA", title_style),
            Paragraph(f"Nº: #{repair_id}", subtitle_style),
            Paragraph(f"Data: {formatted_date}", subtitle_style)
        ]
        
        # Header Table (Fixed widths: Logo 250 pts, Title 265 pts)
        LOGO_COL_WIDTH_PT = 250.0
        TITLE_COL_WIDTH_PT = 265.0
        
        header_table = Table(
            [[logo_cell, invoice_info]],
            colWidths=[LOGO_COL_WIDTH_PT, TITLE_COL_WIDTH_PT]
        )
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),  # Logo left-aligned
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),  # Title right-aligned
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),  # Logo vertically centered
            ('VALIGN', (1, 0), (1, 0), 'TOP'),  # Title top-aligned
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15)
        ]))
        
        story.append(header_table)
        
        # Horizontal Line (using Table for simplicity)
        line_table = Table([[""]], colWidths=[AVAILABLE_WIDTH_PT], rowHeights=[2])
        line_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), line_color),
            ('LINEBELOW', (0, 0), (-1, -1), 0, colors.white)
        ]))
        story.append(line_table)
        story.append(Spacer(1, 0.6*cm))
        
        # ========== SECTION 2: INFO BLOCK (2 COLUMNS) ==========
        # Horizontal line before info block
        line_table_before = Table([[""]], colWidths=[AVAILABLE_WIDTH_PT], rowHeights=[1])
        line_table_before.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), line_color),
            ('LINEBELOW', (0, 0), (-1, -1), 0, colors.white)
        ]))
        story.append(line_table_before)
        story.append(Spacer(1, 0.3*cm))
        
        client_name = repair_data.get("client", "N/A")
        client_nif = repair_data.get("client_nif", "") or ""
        client_address = repair_data.get("client_address", "") or ""
        client_phone = repair_data.get("client_phone", "") or ""
        device_imei = repair_data.get("device_imei", "") or ""
        warranty_number = repair_data.get("warranty_number", "") or ""
        problem_summary = repair_data.get("problem_summary", "") or ""
        
        # Left Column: CLIENTE
        client_lines = [Paragraph("CLIENTE", section_header_style)]
        client_lines.append(Paragraph(client_name, normal_text_style))
        if client_phone:
            client_lines.append(Paragraph(client_phone, normal_text_style))
        if client_nif:
            client_lines.append(Paragraph(f"NIF: {client_nif}", normal_text_style))
        if client_address:
            client_lines.append(Paragraph(client_address, normal_text_style))
        
        # Right Column: DETALHES DO SERVIÇO
        service_lines = [Paragraph("DETALHES DO SERVIÇO", section_header_style)]
        if device_imei:
            service_lines.append(Paragraph(f"IMEI / Nº Série: {device_imei}", normal_text_style))
        if warranty_number:
            service_lines.append(Paragraph(f"Nº Garantia: {warranty_number}", normal_text_style))
        if problem_summary:
            service_lines.append(Paragraph(f"Tipo de Equipamento: {problem_summary}", normal_text_style))
        
        # Balance columns (add empty lines if needed)
        max_lines = max(len(client_lines), len(service_lines))
        while len(client_lines) < max_lines:
            client_lines.append(Paragraph("", normal_text_style))
        while len(service_lines) < max_lines:
            service_lines.append(Paragraph("", normal_text_style))
        
        # Info Block Table (Fixed widths: 50% / 50% of available width)
        INFO_COL_WIDTH_PT = AVAILABLE_WIDTH_PT / 2.0
        info_table = Table(
            [[client_lines, service_lines]],
            colWidths=[INFO_COL_WIDTH_PT, INFO_COL_WIDTH_PT]
        )
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ]))
        
        story.append(info_table)
        
        # Horizontal line after info block
        line_table_after = Table([[""]], colWidths=[AVAILABLE_WIDTH_PT], rowHeights=[1])
        line_table_after.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), line_color),
            ('LINEBELOW', (0, 0), (-1, -1), 0, colors.white)
        ]))
        story.append(Spacer(1, 0.3*cm))
        story.append(line_table_after)
        story.append(Spacer(1, 0.4*cm))
        
        # Description (if available)
        description = repair_data.get("description", "")
        if description:
            story.append(Paragraph("<b>Descrição Detalhada:</b>", section_header_style))
            story.append(Paragraph(description, normal_text_style))
            story.append(Spacer(1, 0.4*cm))
        
        # ========== SECTION 3: ITEMS TABLE ==========
        used_parts_str = repair_data.get("used_parts", "")
        parts_list = []
        
        if used_parts_str and used_parts_str.strip() and used_parts_str != "Nenhum":
            # Parse componentes usando o método do db_manager para suportar ambos os formatos
            if db_manager:
                parsed_components = db_manager._parse_used_parts(used_parts_str)
            else:
                # Fallback se db_manager não estiver disponível
                parsed_components = []
                if "," in used_parts_str:
                    parts = used_parts_str.split(",")
                else:
                    parts = [used_parts_str]
                
                for part in parts:
                    part = part.strip()
                    if ":" in part and "(" not in part:
                        # Novo formato: ID:QTY
                        try:
                            comp_id_str, qty_str = part.split(":", 1)
                            parsed_components.append((int(comp_id_str.strip()), int(qty_str.strip())))
                        except (ValueError, AttributeError):
                            continue
                    elif "(" in part and ")" in part:
                        # Formato antigo: Code (Qty)
                        code = part.split("(")[0].strip()
                        qty_str = part.split("(")[1].split(")")[0].strip().replace("x", "")
                        try:
                            qty = int(qty_str)
                            parsed_components.append((code, qty))
                        except:
                            parsed_components.append((code, 1))
                    else:
                        parsed_components.append((part.strip(), 1))
            
            for id_or_code, qty in parsed_components:
                code = ""
                name = ""
                price = 0.0
                
                # Buscar componente na base de dados
                if db_manager:
                    if isinstance(id_or_code, int):
                        # É um ID (formato novo)
                        component = db_manager.get_component_by_id(id_or_code)
                    else:
                        # É um código (formato antigo)
                        component = db_manager.get_component_by_code(id_or_code)
                    
                    if component:
                        code = component.get("code", str(id_or_code))
                        name = component.get("name", code)
                        price = component.get("price", 0.0)
                    else:
                        # Componente não encontrado
                        if isinstance(id_or_code, int):
                            code = f"ID {id_or_code}"
                        else:
                            code = id_or_code
                        name = code
                else:
                    # Fallback se db_manager não estiver disponível
                    if isinstance(id_or_code, int):
                        code = f"ID {id_or_code}"
                    else:
                        code = id_or_code
                    name = code
                
                total = price * qty
                parts_list.append({
                    "code": code,
                    "name": name,
                    "qty": qty,
                    "price": price,
                    "total": total
                })
        
        # Adicionar linha de testes/diagnóstico se aplicável
        horas_teste = float(repair_data.get("horas_teste", 0.0) or 0.0)
        preco_hora_teste = float(repair_data.get("preco_hora_teste", 0.0) or 0.0)
        
        if horas_teste > 0 and preco_hora_teste > 0:
            test_total = horas_teste * preco_hora_teste
            # Armazenar qty como string formatada para exibição no PDF
            parts_list.append({
                "code": "TESTE",
                "name": "Serviço de Teste e Diagnóstico",
                "qty": f"{horas_teste:.1f} h",  # Formato: "X.X h"
                "price": preco_hora_teste,
                "total": test_total
            })
        
        # Create Items Table
        if parts_list:
            # Dynamic column widths in points: [Code, Description, Qty, Unit Price, Total]
            # The code column expands to fit the longest code in this repair, while
            # the last three numeric columns stay compact.
            col_widths = _calculate_items_table_widths(parts_list, AVAILABLE_WIDTH_PT)
            
            # Define fixed headers as simple strings (NOT Paragraph objects)
            # This ensures they respect TableStyle TEXTCOLOR (White on dark blue)
            headers = ["Código", "Designação", "Qtd", "Preço Un.", "Total"]
            
            # Initialize data list with headers as the first row
            items_table_data = [headers]
            
            # Append body rows with Paragraph objects for proper alignment
            for part in parts_list:
                row = [
                    Paragraph(part["code"], table_text_style),  # Left-aligned (default)
                    Paragraph(part["name"], table_text_style),  # Left-aligned (default)
                    Paragraph(str(part["qty"]), style_center),  # Center-aligned
                    Paragraph(format_currency(part["price"]), style_right),  # Right-aligned
                    Paragraph(format_currency(part["total"]), style_right)  # Right-aligned
                ]
                items_table_data.append(row)
            
            items_table = Table(items_table_data, colWidths=col_widths)
            items_table.setStyle(TableStyle([
                # Header Design
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                
                # DATA ALIGNMENT (Fixing the floating numbers)
                ('ALIGN', (0, 0), (1, -1), 'LEFT'),    # Code & Desc -> Align Left
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Qty -> Align Center
                ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),   # Price & Total -> Align RIGHT
                
                # Body Row Styling
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2C3E50')),
                
                # ROW COLORS (Zebra Effect)
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, colors.HexColor('#F4F6F7')]),
                
                # PADDING CORRECTION
                # Give numbers space from the right edge so they don't look cramped, but align correctly
                ('RIGHTPADDING', (3, 0), (-1, -1), 6),  # Price & Total columns stay compact
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                
                # Borders
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.white),
                ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
            ]))
            
            story.append(items_table)
        else:
            story.append(Paragraph("Nenhum componente registado", normal_text_style))
        
        story.append(Spacer(1, 0.6*cm))
        
        # ========== SECTION 4: TOTALS & BREAKDOWN (BOTTOM RIGHT) ==========
        # Calcular valores
        qty = float(repair_data.get("hours_worked", 1.0) or 1.0)  # Agora genérico (horas ou unidades)
        labor_type = repair_data.get("labor_type", "labor1")  # 'labor1', 'labor2', ou 'placas'
        electricity_hours = float(repair_data.get("electricity_hours", 0.0) or 0.0)
        electricity_rate = float(repair_data.get("electricity_rate", 0.50) or 0.50)
        package_weight = float(repair_data.get("package_weight", 0.0) or 0.0)
        transport_cost = float(repair_data.get("transport_cost", 0.0) or 0.0)
        
        # Obter taxa baseada no tipo de mão de obra
        if db_manager:
            if labor_type == "labor1":
                rate = float(db_manager.get_setting("labor_rate_1", "30.0"))
                labor_label = f"Mão de Obra 1 ({qty:.1f} h)"
            elif labor_type == "labor2":
                rate = float(db_manager.get_setting("labor_rate_2", "45.0"))
                labor_label = f"Mão de Obra 2 ({qty:.1f} h)"
            elif labor_type == "placas":
                rate = float(db_manager.get_setting("placas_price", "50.0"))
                labor_label = f"Reparação Placa ({qty:.0f} un)"
            else:
                # Fallback
                rate = float(db_manager.get_setting("labor_rate_1", "30.0"))
                labor_label = f"Mão de Obra ({qty:.1f} h)"
        else:
            # Fallback se db_manager não estiver disponível
            rate = 30.0
            if labor_type == "labor2":
                rate = 45.0
                labor_label = f"Mão de Obra 2 ({qty:.1f} h)"
            elif labor_type == "placas":
                rate = 50.0
                labor_label = f"Reparação Placa ({qty:.0f} un)"
            else:
                labor_label = f"Mão de Obra 1 ({qty:.1f} h)"
        
        labor_total = qty * rate
        elec_total = electricity_hours * electricity_rate
        parts_total = sum(part["total"] for part in parts_list)
        
        # Incluir custo de testes no total (já está incluído em parts_total se horas_teste > 0)
        # Não precisamos adicionar novamente, pois já foi adicionado à lista de componentes
        net_total = parts_total + labor_total + elec_total + transport_cost
        vat_rate = 0.23
        vat_amount = net_total * vat_rate
        final_total = net_total + vat_amount
        
        # ========== SECTION 4: TOTALS TABLE (Fixed widths, right-aligned) ==========
        # Fixed column widths: Label 150 pts, Value 100 pts (total 250 pts)
        TOTALS_LABEL_WIDTH_PT = 150.0
        TOTALS_VALUE_WIDTH_PT = 100.0
        TOTALS_TABLE_WIDTH_PT = TOTALS_LABEL_WIDTH_PT + TOTALS_VALUE_WIDTH_PT  # 250 pts
        
        totals_data = []
        # Normal rows: Labels use table_text_style (left), Values use style_totals_right (right-aligned)
        totals_data.append([Paragraph("Subtotal Peças", table_text_style), Paragraph(format_currency(parts_total), style_totals_right)])
        totals_data.append([Paragraph(labor_label, table_text_style), Paragraph(format_currency(labor_total), style_totals_right)])
        
        if electricity_hours > 0:
            totals_data.append([Paragraph(f"Eletricidade ({electricity_hours:.1f} h)", table_text_style), Paragraph(format_currency(elec_total), style_totals_right)])
        
        if transport_cost > 0:
            totals_data.append([Paragraph(f"Transporte ({package_weight:.2f} kg)", table_text_style), Paragraph(format_currency(transport_cost), style_totals_right)])
        
        totals_data.append([Paragraph("Subtotal Líquido", table_text_style), Paragraph(format_currency(net_total), style_totals_right)])
        totals_data.append([Paragraph("IVA (23%)", table_text_style), Paragraph(format_currency(vat_amount), style_totals_right)])
        
        # Grand Total Row (highlighted): Use style_total_final for both label and value
        totals_data.append([
            Paragraph("TOTAL", style_total_final),  # White, bold, right-aligned label
            Paragraph(format_currency(final_total), style_total_final)  # White, bold, right-aligned value
        ])
        
        totals_table = Table(totals_data, colWidths=[TOTALS_LABEL_WIDTH_PT, TOTALS_VALUE_WIDTH_PT])
        
        # Determine number of regular rows (before Grand Total)
        num_regular_rows = len(totals_data) - 1
        
        totals_table.setStyle(TableStyle([
            # Normal rows (Subtotal through IVA)
            ('TEXTCOLOR', (0, 0), (-1, num_regular_rows - 1), colors.HexColor('#2C3E50')),
            ('FONTNAME', (0, 0), (-1, num_regular_rows - 1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, num_regular_rows - 1), 9),
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Labels left-aligned
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),  # Values right-aligned
            # Padding
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            # Thin lines under each value cell (like account ledger)
            ('LINEBELOW', (1, 0), (1, num_regular_rows - 1), 0.5, line_color),
            # Grand Total row (last row)
            ('BACKGROUND', (0, -1), (-1, -1), secondary_color),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            # No line under Grand Total
        ]))
        
        # Right-align the entire totals table
        right_aligned_table = Table([[totals_table]], colWidths=[AVAILABLE_WIDTH_PT])
        right_aligned_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (0, 0), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 0)
        ]))
        
        story.append(right_aligned_table)
        story.append(Spacer(1, 0.4*cm))
        
        # Payment Status
        payment_status = repair_data.get("payment_status", "Pendente")
        status_color = colors.HexColor('#4CAF50') if payment_status == "Pago" else colors.HexColor('#FF9800')
        status_style = ParagraphStyle(
            'PaymentStatus',
            parent=normal_text_style,
            fontSize=9,
            textColor=status_color,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        )
        status_para = Paragraph(f"Estado: {payment_status}", status_style)
        story.append(status_para)
        
        story.append(Spacer(1, 0.8*cm))
        
        # ========== SECTION 5: FOOTER ==========
        footer_text = "Documento processado por computador. Garantia de 3 meses sobre a reparação."
        footer = Paragraph(footer_text, footer_style)
        story.append(footer)
        
        # Construir PDF
        doc.build(story)
        
        return True
    
    except Exception as e:
        print(f"Erro ao gerar PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return False
