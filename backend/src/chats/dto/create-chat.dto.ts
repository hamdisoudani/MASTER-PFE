import { IsString, IsNotEmpty, MaxLength } from 'class-validator';

export class CreateChatDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  title!: string;
}
